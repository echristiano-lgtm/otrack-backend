# parser_iof.py
import xmltodict

def parse_iof_xml(xml_bytes: bytes):
    """
    Converte IOF XML em um dicionário no shape que o frontend já entende:
    {
      id: str,
      name: str,
      date: 'YYYY-MM-DD' | '',
      classes: {
        [className]: {
          name: str,
          competitors: [{
            id, name, club, status, pos, timeS,
            splits: [{seq, code, split?, cum?}]
          }]
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
    # date pode variar no IOF; mantenha simples (opcional)
    event_date = (ev_node.get("StartTime") or ev_node.get("StartDate") or "") or ""
    if isinstance(event_date, dict) and "Date" in event_date:
        event_date = str(event_date["Date"])
    event_date = str(event_date)[:10] if event_date else ""

    classes = {}
    class_results = rl.get("ClassResult") or []
    if isinstance(class_results, dict):
        class_results = [class_results]

    for cr in class_results:
        cls_name = ((cr.get("Class") or {}).get("Name") or "Classe").strip()
        prs = cr.get("PersonResult") or []
        if isinstance(prs, dict):
            prs = [prs]

        competitors = []
        for pr in prs:
            # nome
            person = pr.get("Person") or {}
            pname = person.get("Name") or {}
            family = pname.get("Family") or ""
            given = pname.get("Given") or ""
            name = f"{given} {family}".strip() or "(sem nome)"

            # clube
            org = (pr.get("Organisation") or {}).get("Name") or ""

            res = pr.get("Result") or {}
            status = res.get("Status") or "OK"

            # tempo total (segundos)
            time_s = res.get("Time")
            try:
                time_s = int(time_s) if time_s is not None else None
            except:
                time_s = None

            pos = res.get("Position")
            # ID: tente pegar do XML; se não houver, gera um
            pid = person.get("@id") or pr.get("@id") or f"p-{len(competitors)+1}"

            # splits (deriva split do cumulativo se preciso)
            splits = []
            sp = res.get("SplitTime") or []
            if isinstance(sp, dict):
                sp = [sp]

            seq = 1
            last_cum = 0
            for st in sp:
                code = st.get("ControlCode")
                # IOF costuma dar cumulativo em SplitTime.Time
                cum = st.get("Time")
                try:
                    cum = int(cum) if cum is not None else None
                except:
                    cum = None

                split_val = None
                if isinstance(cum, int):
                    split_val = cum - last_cum if last_cum else cum
                    last_cum = cum

                splits.append({
                    "seq": seq, "code": code, "split": split_val, "cum": cum
                })
                seq += 1

            competitors.append({
                "id": pid, "name": name, "club": org,
                "status": status, "pos": pos, "timeS": time_s,
                "splits": splits
            })

        classes[cls_name] = {"name": cls_name, "competitors": competitors}

    return {
        "id": "", "name": event_name, "date": event_date, "classes": classes
    }