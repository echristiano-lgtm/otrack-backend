# main.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List, Optional
import hashlib, json, os, unicodedata
import xmltodict  # pip install xmltodict

# ===============================
# App & CORS
# ===============================
app = FastAPI(title="MEOS Backend", version="1.2.0")

ALLOWED_ORIGINS = os.environ.get(
    "MEOS_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173",
)
origins = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.getcwd()
DATA_DIR = os.environ.get("MEOS_DATA_DIR", os.path.join(BASE_DIR, "data"))
os.makedirs(DATA_DIR, exist_ok=True)

# ===============================
# Admin
# ===============================
ADMIN_TOKEN = os.environ.get("MEOS_ADMIN_TOKEN", "")

def require_admin(req: Request):
    token = req.headers.get("x-admin-token") or ""
    if not ADMIN_TOKEN or token != ADMIN_TOKEN:
        print("⚠️ Tentativa de ação admin com token inválido:", token)
        raise HTTPException(status_code=403, detail="Forbidden")

# ===============================
# Utils (armazenamento & helpers)
# ===============================
def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip() or "event"

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s

def build_event_index(ev: Dict[str, Any]) -> Dict[str, Any]:
    idx = {"athletesByName": {}, "clubs": set(), "classes": list((ev.get("classes") or {}).keys())}
    for cls_name, cls in (ev.get("classes") or {}).items():
        for c in (cls.get("competitors") or []):
            nm = (c.get("name") or "").strip().lower()
            if nm:
                idx["athletesByName"].setdefault(nm, []).append(
                    {"eid": ev.get("id"), "className": cls_name, "id": c.get("id")}
                )
            if c.get("club"):
                idx["clubs"].add(c["club"])
    idx["clubs"] = sorted(idx["clubs"])
    return idx

def save_event(ev: Dict[str, Any]) -> Dict[str, Any]:
    # ID determinístico por nome+data+classes (sem courseData p/ estabilidade)
    payload = json.dumps(
        {
            "name": ev["name"],
            "date": ev["date"],
            "organizer": ev.get("organizer", ""),
            "classes": ev["classes"],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    eid = sha1_bytes(payload)[:12]
    ev["id"] = eid
    ev["__index"] = build_event_index(ev)

    path = os.path.join(DATA_DIR, f"{safe_filename(eid)}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ev, f, ensure_ascii=False)
    return ev

def load_event(eid: str) -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, f"{safe_filename(eid)}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(eid)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def list_events() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for fn in os.listdir(DATA_DIR):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(DATA_DIR, fn), "r", encoding="utf-8") as f:
            ev = json.load(f)
        out[ev["id"]] = {
            "id": ev["id"],
            "name": ev.get("name"),
            "date": ev.get("date"),
            "organizer": ev.get("organizer", ""),
            "classesCount": len((ev.get("classes") or {})),
            "hasCourseData": bool(ev.get("courseData") or ev.get("courseMetrics")),
        }
    return out

def delete_event(eid: str) -> bool:
    path = os.path.join(DATA_DIR, f"{safe_filename(eid)}.json")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False

# ===============================
# Parsers IOF
# ===============================
def parse_iof_xml(xml_bytes: bytes) -> Dict[str, Any]:
    """
    Converte IOF XML (ResultList) para o shape do frontend:
    {
      id: str,
      name: str,
      date: 'YYYY-MM-DD' | '',
      organizer: str,
      classes: {
        [className]: {
          name: str,
          competitors: [ { id, name, club, status, pos, timeS, splits: [ {seq, code, split?, cum?} ] } ]
        }
      }
    }
    """
    if len(xml_bytes) > 10 * 1024 * 1024:
        raise ValueError("Arquivo muito grande (limite 10MB).")

    doc = xmltodict.parse(xml_bytes, disable_entities=True)

    rl = doc.get("ResultList") or {}
    ev_node = rl.get("Event") or {}

    event_name = (ev_node.get("Name") or rl.get("Name") or "Evento").strip()

    event_date = (
        ev_node.get("StartTime")
        or ev_node.get("StartDate")
        or rl.get("StartTime")
        or rl.get("StartDate")
        or ""
    )
    if isinstance(event_date, dict) and "Date" in event_date:
        event_date = str(event_date["Date"])
    event_date = str(event_date)[:10] if event_date else ""

    organizer = ""
    org_node = ev_node.get("Organiser") or ev_node.get("Organizer") or ev_node.get("OrganisingClub") or {}
    if isinstance(org_node, dict):
        organizer = org_node.get("Name") or org_node.get("ShortName") or ""
    elif isinstance(org_node, str):
        organizer = org_node
    if not organizer:
        tmp = rl.get("Organizer") or rl.get("Organiser") or {}
        if isinstance(tmp, dict):
            organizer = tmp.get("Name") or ""

    classes: Dict[str, Any] = {}
    class_results = rl.get("ClassResult") or []
    if isinstance(class_results, dict):
        class_results = [class_results]

    for cr in class_results:
        cls_name = ((cr.get("Class") or {}).get("Name") or "Classe").strip()

        prs = cr.get("PersonResult") or []
        if isinstance(prs, dict):
            prs = [prs]

        competitors: List[Dict[str, Any]] = []
        for pr in prs:
            person = pr.get("Person") or {}
            pname = person.get("Name") or {}
            family = pname.get("Family") or ""
            given = pname.get("Given") or ""
            name = f"{given} {family}".strip() or "(sem nome)"

            org = (pr.get("Organisation") or {}).get("Name") or ""
            res = pr.get("Result") or {}
            status = res.get("Status") or "OK"

            time_s = res.get("Time")
            try:
                time_s = int(time_s) if time_s is not None else None
            except Exception:
                time_s = None

            pos = res.get("Position")
            pid = person.get("@id") or pr.get("@id") or f"p-{len(competitors)+1}"

            splits = []
            sp = res.get("SplitTime") or []
            if isinstance(sp, dict):
                sp = [sp]

            seq = 1
            last_cum = 0
            for st in sp:
                code = st.get("ControlCode")
                cum = st.get("Time")
                try:
                    cum = int(cum) if cum is not None else None
                except Exception:
                    cum = None

                split_val = None
                if isinstance(cum, int):
                    split_val = cum - last_cum if last_cum else cum
                    last_cum = cum

                splits.append({"seq": seq, "code": code, "split": split_val, "cum": cum})
                seq += 1

            competitors.append(
                {
                    "id": pid,
                    "name": name,
                    "club": org,
                    "status": status,
                    "pos": pos,
                    "timeS": time_s,
                    "splits": splits,
                }
            )

        classes[cls_name] = {"name": cls_name, "competitors": competitors}

    return {
        "id": "",
        "name": event_name,
        "date": event_date,
        "organizer": organizer or "",
        "classes": classes,
    }

def _to_number(x):
    if x is None:
        return None
    s = str(x).strip().replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None

def _pick_length(obj):
    return (
        _to_number(obj.get("Length"))
        or _to_number(obj.get("CourseLength"))
        or _to_number(obj.get("LengthInMeter"))
        or (_to_number(obj.get("LengthInKm")) * 1000 if _to_number(obj.get("LengthInKm")) else None)
    )

def _pick_climb(obj):
    return (
        _to_number(obj.get("Climb"))
        or _to_number(obj.get("CourseClimb"))
        or _to_number(obj.get("ClimbInMeter"))
    )

def _pick_classname(node):
    if not isinstance(node, dict):
        return None
    return (
        (node.get("Class", {}) or {}).get("Name")
        or (node.get("Class", {}) or {}).get("ShortName")
        or node.get("ClassName")
        or node.get("Name")
    )

def parse_course_xml(xml_bytes: bytes) -> Dict[str, Any]:
    """Parse genérico do IOF CourseData; mantemos “cru” para debug/uso futuro."""
    try:
        doc = xmltodict.parse(xml_bytes, disable_entities=True)
        return doc or {}
    except Exception:
        return {}

def extract_course_metrics(course_doc: dict) -> dict:
    """Extrai { className: {lengthM, climbM} } de CourseData em variações comuns."""
    if not course_doc:
        return {}
    root = course_doc.get("CourseData") or course_doc

    metrics: Dict[str, Dict[str, float]] = {}

    # 1) ClassCourse[] (com Course.{Length,Climb})
    cc = root.get("ClassCourse")
    if cc:
        cc_list = cc if isinstance(cc, list) else [cc]
        for it in cc_list:
            cls = _pick_classname(it)
            if not cls:
                continue
            course = it.get("Course") or it
            length = _pick_length(course)
            climb = _pick_climb(course)
            if length is not None or climb is not None:
                metrics.setdefault(cls, {})
                if length is not None:
                    metrics[cls]["lengthM"] = float(length)
                if climb is not None:
                    metrics[cls]["climbM"] = float(climb)

    # 2) Course[] (com ClassName ou Name)
    crs = root.get("Course") or root.get("Courses")
    if crs:
        crs_list = crs if isinstance(crs, list) else [crs]
        for c in crs_list:
            cls = c.get("ClassName") or (c.get("Class") or {}).get("Name") or c.get("Name")
            length = _pick_length(c)
            climb = _pick_climb(c)
            if not cls:
                if len(crs_list) == 1 and (length is not None or climb is not None):
                    metrics.setdefault("_GENERIC_", {})
                    if length is not None:
                        metrics["_GENERIC_"]["lengthM"] = float(length)
                    if climb is not None:
                        metrics["_GENERIC_"]["climbM"] = float(climb)
                continue
            if length is not None or climb is not None:
                metrics.setdefault(cls, {})
                if length is not None:
                    metrics[cls]["lengthM"] = float(length)
                if climb is not None:
                    metrics[cls]["climbM"] = float(climb)

    return metrics

def _merge_course_into_event(ev: Dict[str, Any], metrics: Dict[str, Dict[str, float]]):
    """Atribui length/climb por classe (match case/acento-insensitive) e guarda agregado em ev['courseMetrics']."""
    if not metrics:
        return
    by_norm = {_norm(k): v for k, v in metrics.items()}

    for cls_name, cls in (ev.get("classes") or {}).items():
        n = _norm(cls_name)
        payload = by_norm.get(n)
        if payload is None and "_GENERIC_" in metrics:
            payload = metrics["_GENERIC_"]
        if payload:
            cls.setdefault("course", {})
            if "lengthM" in payload:
                cls["course"]["lengthM"] = payload["lengthM"]
            if "climbM" in payload:
                cls["course"]["climbM"] = payload["climbM"]

    ev["courseMetrics"] = metrics

# ===============================
# Rotas
# ===============================
@app.get("/api/health")
def health():
    return {"ok": True}

@app.get("/api/events")
def api_list():
    return list_events()

@app.get("/api/events/{eid}/blob")
def api_get_blob(eid: str):
    try:
        return load_event(eid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

@app.get("/api/events/{eid}/classes")
def api_get_classes(eid: str):
    """Resumo por classe (nome, contagem, length/climb)"""
    try:
        ev = load_event(eid)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    out = []
    for k, v in (ev.get("classes") or {}).items():
        comp = v.get("competitors") or []
        course = (v.get("course") or {})
        out.append(
            {
                "name": k,
                "competitors": len(comp),
                "lengthM": course.get("lengthM"),
                "climbM": course.get("climbM"),
            }
        )
    return {"event": {"id": ev.get("id"), "name": ev.get("name")}, "classes": out}

@app.delete("/api/events/{eid}")
def api_delete_event(eid: str, req: Request):
    require_admin(req)
    ok = delete_event(eid)
    if not ok:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return {"ok": True}

@app.post("/api/events/import")
async def import_event(
    result: UploadFile = File(..., description="IOF ResultList (.xml/.iof/.html/.htm)"),
    course: Optional[UploadFile] = File(None, description="IOF CourseData opcional"),
    organizer: Optional[str] = Form(None),
):
    allowed = (".xml", ".iof", ".html", ".htm")

    # --- Resultados (obrigatório)
    if not result.filename.lower().endswith(allowed):
        raise HTTPException(status_code=400, detail="Resultados devem ser IOF XML (.xml/.iof/.html/.htm)")
    res_bytes = await result.read()
    head = res_bytes[:4096].decode(errors="ignore").lower()
    if "<resultlist" not in head and "<xml" not in head:
        raise HTTPException(status_code=400, detail="Arquivo de resultados não parece conter IOF ResultList válido.")
    ev = parse_iof_xml(res_bytes)

    # --- Percurso (opcional)
    course_parsed: Dict[str, Any] = {}
    if course is not None:
        if not course.filename.lower().endswith(allowed):
            raise HTTPException(status_code=400, detail="Percurso deve ser IOF XML (.xml/.iof/.html/.htm)")
        c_bytes = await course.read()
        course_parsed = parse_course_xml(c_bytes)

        course_metrics = extract_course_metrics(course_parsed)
        if course_metrics:
            _merge_course_into_event(ev, course_metrics)
            ev["courseData"] = course_parsed  # mantemos bruto p/ debug
        else:
            ev["courseData"] = course_parsed  # mesmo sem métricas, guarda

    # --- Organizer sobrescreve se vier no form
    if organizer:
        org = organizer.strip()
        if org:
            ev["organizer"] = org

    try:
        ev = save_event(ev)
        return {
            "id": ev["id"],
            "name": ev["name"],
            "date": ev.get("date"),
            "organizer": ev.get("organizer", ""),
            "classesCount": len(ev.get("classes", {})),
            "hasCourseData": bool(ev.get("courseData")),
            "hasCourseMetrics": bool(ev.get("courseMetrics")),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no processamento: {e}")
