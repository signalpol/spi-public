import json, time, requests, traceback

BASE = "http://127.0.0.1:8080"
SEED_PATH = "/tmp/sfpf_validation_001_seed.txt"
REQ = (
    "Using only information available through 2025-04-02, simulate the next 7–14 days after the U.S. reciprocal tariff announcement. "
    "Forecast actor interactions among the United States, China, other major trading partners, financial markets, U.S. political actors, and economic actors. "
    "Identify the base future pathway, competing pathway, escalation/de-escalation triggers, market reaction, policy adjustment, turning point, and consequences. "
    "Do not assume or import knowledge of events after 2025-04-02."
)
SEED = """SFPF VALIDATION #001 — TEMPORAL CUTOFF 2025-04-02

Source: The White House, Fact Sheet and Executive Order 14257, April 2, 2025.

Known information as of the cutoff:
1. President Donald Trump declared a national emergency over persistent U.S. goods trade deficits and non-reciprocal trade practices.
2. The United States announced an additional 10% tariff on imports from all trading partners, effective April 5, 2025.
3. Higher individualized reciprocal tariffs were announced for countries with the largest U.S. trade deficits, effective April 9, 2025.
4. The order explicitly provides authority to increase tariffs if trading partners retaliate and to reduce tariffs if trading partners take significant steps to remedy non-reciprocal trade arrangements and align with U.S. economic and national-security objectives.
5. Canada and Mexico remain primarily under the existing fentanyl/migration IEEPA tariff framework rather than the new country-specific reciprocal tariff schedule.

Forecast task:
Using only the information contained in this document and general pre-cutoff structural knowledge, simulate how the United States, China, other major trading partners, financial markets, U.S. political actors, and economic actors may interact over the next 7–14 days. Identify the most plausible future pathway, meaningful competing pathways, likely retaliation, market reactions, policy adjustments, escalation or de-escalation triggers, and turning points. Do not assume knowledge of events after April 2, 2025.
"""


def out(tag, obj):
    print("SFPF_BT001::" + tag + "::" + json.dumps(obj, ensure_ascii=False), flush=True)


def req(method, path, **kw):
    r = requests.request(method, BASE + path, timeout=180, **kw)
    try:
        j = r.json()
    except Exception:
        j = {"text": r.text[:4000]}
    out("HTTP_" + path.replace("/", "_"), {"code": r.status_code, "body": j})
    r.raise_for_status()
    return j


def poll_graph(task_id, timeout=1200):
    t = time.time()
    while time.time() - t < timeout:
        d = req("GET", f"/api/graph/task/{task_id}").get("data", {})
        s = str(d.get("status", "")).lower()
        if s in ("completed", "failed"):
            return d
        time.sleep(10)
    raise TimeoutError("graph build timeout")


def poll_prepare(task_id, sim_id, timeout=1500):
    t = time.time()
    while time.time() - t < timeout:
        d = req("POST", "/api/simulation/prepare/status", json={"task_id": task_id, "simulation_id": sim_id}).get("data", {})
        s = str(d.get("status", "")).lower()
        if s in ("completed", "ready", "failed"):
            return d
        time.sleep(10)
    raise TimeoutError("prepare timeout")


def poll_run(sim_id, timeout=1800):
    t = time.time()
    last = None
    while time.time() - t < timeout:
        d = req("GET", f"/api/simulation/{sim_id}/run-status").get("data", {})
        last = d
        s = str(d.get("runner_status", "")).lower()
        if s in ("completed", "stopped", "failed"):
            return d
        time.sleep(10)
    raise TimeoutError("run timeout last=" + repr(last))


try:
    for _ in range(60):
        try:
            r = requests.get(BASE + "/api/graph/project/list", timeout=3)
            if r.status_code < 500:
                break
        except Exception:
            pass
        time.sleep(2)

    with open(SEED_PATH, "w", encoding="utf-8") as f:
        f.write(SEED)

    out("RUN_META", {
        "cutoff": "2025-04-02",
        "seed_sha256": "d0eb31315a2326c0beaedf67689ae6f95b207f4760b51d8d3891079a22f66bf3",
        "engine_commit": "985f89f49acbb44ee14d9d680682c741a44eeebe"
    })

    with open(SEED_PATH, "rb") as f:
        j = req(
            "POST", "/api/graph/ontology/generate",
            files={"files": ("sfpf_validation_001_seed.txt", f, "text/plain")},
            data={
                "simulation_requirement": REQ,
                "project_name": "SFPF Validation 001 - Trump Tariffs 2025-04-02",
                "additional_context": "Historical temporal-cutoff validation. Treat post-cutoff events as unknown."
            }
        )

    pid = j["data"]["project_id"]
    out("PROJECT_ID", {"project_id": pid})

    j = req("POST", "/api/graph/build", json={
        "project_id": pid,
        "graph_name": "SFPF-BT001-2025-04-02",
        "chunk_size": 500,
        "chunk_overlap": 50
    })
    gtask = j["data"]["task_id"]
    gd = poll_graph(gtask)
    if str(gd.get("status", "")).lower() == "failed":
        raise RuntimeError("graph failed " + repr(gd))

    pj = req("GET", f"/api/graph/project/{pid}")
    gid = pj["data"].get("graph_id")
    out("GRAPH_ID", {"graph_id": gid})

    j = req("POST", "/api/simulation/create", json={
        "project_id": pid,
        "graph_id": gid,
        "enable_twitter": False,
        "enable_reddit": True
    })
    sid = j["data"]["simulation_id"]
    out("SIMULATION_ID", {"simulation_id": sid})

    j = req("POST", "/api/simulation/prepare", json={
        "simulation_id": sid,
        "use_llm_for_profiles": True,
        "parallel_profile_count": 2,
        "force_regenerate": False
    })
    if not j["data"].get("already_prepared"):
        ptask = j["data"]["task_id"]
        pd = poll_prepare(ptask, sid)
        if str(pd.get("status", "")).lower() == "failed":
            raise RuntimeError("prepare failed " + repr(pd))

    cfg = req("GET", f"/api/simulation/{sid}/config")
    out("CONFIG_SUMMARY", {
        "time_config": cfg.get("data", {}).get("time_config"),
        "event_config": cfg.get("data", {}).get("event_config")
    })

    req("POST", "/api/simulation/start", json={
        "simulation_id": sid,
        "platform": "reddit",
        "max_rounds": 10,
        "enable_graph_memory_update": True,
        "force": False
    })
    rd = poll_run(sid)
    out("RUN_TERMINAL", rd)

    hist = req("GET", "/api/simulation/history?limit=10")
    out("HISTORY", hist)
    out("DONE", {"project_id": pid, "graph_id": gid, "simulation_id": sid})
except Exception as e:
    out("FAILED", {"error": str(e), "traceback": traceback.format_exc()})
