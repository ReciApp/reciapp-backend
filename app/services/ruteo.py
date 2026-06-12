import heapq
import json
import math
import os
import threading
import urllib.parse
import urllib.request

# ── Área de cobertura: Puente Piedra, Lima ────────────────────────────────────
_BBOX = "-11.92,-77.11,-11.83,-77.03"   # sur,oeste,norte,este
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CACHE_FILE = os.path.join(_DATA_DIR, "osm_cache.json")

_VELOCIDAD_KMH = 25.0   # velocidad promedio en zona urbana
_UMBRAL_DESVIO_M = 40.0  # metros antes de recalcular ruta

# ── Estado del módulo ─────────────────────────────────────────────────────────
_nodes: dict[int, tuple[float, float]] = {}          # node_id → (lat, lon)
_graph: dict[int, list[tuple[int, float]]] = {}      # node_id → [(vecino_id, km)]
_grafo_listo = False
_init_lock = threading.Lock()
_rutas_activas: dict[int, list[tuple[float, float]]] = {}  # solicitud_id → ruta
_ubicaciones_activas: dict[int, dict] = {}  # solicitud_id → {lat, lon, eta_min}


# ── Geometría ─────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Carga del grafo OSM ───────────────────────────────────────────────────────

_OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def _descargar_osm() -> dict:
    query = (
        "[out:json][timeout:90];\n(\n"
        "  way[\"highway\"~\"^(motorway|trunk|primary|secondary|tertiary|"
        "unclassified|residential|service|living_street|"
        "motorway_link|trunk_link|primary_link|secondary_link|tertiary_link)$\"]\n"
        f"  ({_BBOX});\n);\nout body;\n>;\nout skel qt;\n"
    )
    data = urllib.parse.urlencode({"data": query}).encode()

    ultimo_error: Exception | None = None
    for url in _OVERPASS_MIRRORS:
        req = urllib.request.Request(
            url, data=data,
            headers={"User-Agent": "ReciApp/2.0 (academic project; ruteo Puente Piedra Lima)"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            print(f"Ruteo: mirror {url} falló ({exc}), probando el siguiente…")
            ultimo_error = exc
    raise ultimo_error


def _construir_grafo(osm: dict) -> tuple[dict, dict]:
    nodes: dict[int, tuple[float, float]] = {}
    for el in osm.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (float(el["lat"]), float(el["lon"]))

    graph: dict[int, list[tuple[int, float]]] = {nid: [] for nid in nodes}
    for el in osm.get("elements", []):
        if el["type"] != "way":
            continue
        nds = [n for n in el.get("nodes", []) if n in nodes]
        for i in range(len(nds) - 1):
            a, b = nds[i], nds[i + 1]
            dist = haversine_km(*nodes[a], *nodes[b])
            graph[a].append((b, dist))
            graph[b].append((a, dist))
    return nodes, graph


def _init_grafo() -> None:
    global _nodes, _graph, _grafo_listo
    with _init_lock:
        if _grafo_listo:
            return
        os.makedirs(_DATA_DIR, exist_ok=True)
        try:
            if os.path.exists(_CACHE_FILE):
                with open(_CACHE_FILE, encoding="utf-8") as f:
                    osm = json.load(f)
                print("Ruteo: grafo cargado desde caché.")
            else:
                print("Ruteo: descargando mapa de Puente Piedra (Overpass API)…")
                osm = _descargar_osm()
                with open(_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(osm, f)
                print("Ruteo: mapa guardado en caché.")

            _nodes, _graph = _construir_grafo(osm)
            n_aristas = sum(len(v) for v in _graph.values()) // 2
            print(f"Ruteo: {len(_nodes)} nodos · {n_aristas} aristas listas.")
            _grafo_listo = True
        except Exception as exc:
            print(f"Ruteo: error al inicializar ({exc}). Fallback a línea directa.")


# ── Algoritmo A* ──────────────────────────────────────────────────────────────

def _nearest_node(lat: float, lon: float) -> int:
    return min(_nodes, key=lambda nid: haversine_km(lat, lon, _nodes[nid][0], _nodes[nid][1]))


def _astar(start: int, goal: int) -> list[int]:
    if start == goal:
        return [start]
    gl, go = _nodes[goal]
    open_set: list[tuple[float, int]] = [(0.0, start)]
    came_from: dict[int, int] = {}
    g: dict[int, float] = {start: 0.0}

    while open_set:
        _, cur = heapq.heappop(open_set)
        if cur == goal:
            path = []
            while cur in came_from:
                path.append(cur)
                cur = came_from[cur]
            path.append(start)
            return list(reversed(path))
        for nb, dist in _graph.get(cur, []):
            ng = g.get(cur, float("inf")) + dist
            if ng < g.get(nb, float("inf")):
                came_from[nb] = cur
                g[nb] = ng
                nlat, nlon = _nodes[nb]
                heapq.heappush(open_set, (ng + haversine_km(nlat, nlon, gl, go), nb))
    return []


# ── API pública ───────────────────────────────────────────────────────────────

def grafo_listo() -> bool:
    return _grafo_listo


def longitud_ruta_km(coords: list[tuple[float, float]]) -> float:
    return sum(
        haversine_km(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        for i in range(len(coords) - 1)
    )


def calcular_ruta(
    origen_lat: float, origen_lon: float,
    destino_lat: float, destino_lon: float,
) -> tuple[list[tuple[float, float]], float]:
    """Devuelve (lista_coordenadas, distancia_km). Usa línea directa si el grafo no está listo."""
    if not _grafo_listo or not _nodes:
        dist = haversine_km(origen_lat, origen_lon, destino_lat, destino_lon)
        return [(origen_lat, origen_lon), (destino_lat, destino_lon)], dist

    start = _nearest_node(origen_lat, origen_lon)
    goal = _nearest_node(destino_lat, destino_lon)
    path = _astar(start, goal)

    if not path:
        dist = haversine_km(origen_lat, origen_lon, destino_lat, destino_lon)
        return [(origen_lat, origen_lon), (destino_lat, destino_lon)], dist

    coords = [_nodes[nid] for nid in path]
    return coords, longitud_ruta_km(coords)


# ── Ruta óptima con múltiples puntos (RECI-75) ───────────────────────────────

def _matriz_distancias(
    puntos: list[tuple[float, float]],
) -> tuple[list[list[float]], dict[tuple[int, int], list[tuple[float, float]]]]:
    """Matriz de costos entre todos los pares de puntos usando A* como función
    de costo. El grafo es no dirigido, así que solo se calcula medio triángulo."""
    n = len(puntos)
    dist = [[0.0] * n for _ in range(n)]
    rutas: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for i in range(n):
        for j in range(i + 1, n):
            coords, d = calcular_ruta(puntos[i][0], puntos[i][1], puntos[j][0], puntos[j][1])
            dist[i][j] = dist[j][i] = d
            rutas[(i, j)] = coords
            rutas[(j, i)] = list(reversed(coords))
    return dist, rutas


def _costo_camino(orden: list[int], dist: list[list[float]]) -> float:
    return sum(dist[orden[i]][orden[i + 1]] for i in range(len(orden) - 1))


def _vecino_mas_cercano(dist: list[list[float]]) -> list[int]:
    """Orden inicial de visita: desde el origen (índice 0) saltar siempre
    al punto pendiente más cercano."""
    orden = [0]
    pendientes = set(range(1, len(dist)))
    while pendientes:
        actual = orden[-1]
        siguiente = min(pendientes, key=lambda j: dist[actual][j])
        orden.append(siguiente)
        pendientes.remove(siguiente)
    return orden


def _mejora_2opt(orden: list[int], dist: list[list[float]]) -> list[int]:
    """Mejora 2-opt sobre camino abierto: invierte segmentos mientras reduzcan
    el costo total. El origen (posición 0) queda fijo."""
    mejor = orden[:]
    costo_mejor = _costo_camino(mejor, dist)
    mejorado = True
    while mejorado:
        mejorado = False
        for i in range(1, len(mejor) - 1):
            for k in range(i + 1, len(mejor)):
                candidato = mejor[:i] + mejor[i:k + 1][::-1] + mejor[k + 1:]
                costo = _costo_camino(candidato, dist)
                if costo < costo_mejor - 1e-9:
                    mejor, costo_mejor = candidato, costo
                    mejorado = True
    return mejor


def optimizar_multipunto(
    origen: tuple[float, float],
    paradas: list[tuple[float, float]],
) -> tuple[list[int], list[dict]]:
    """Ordena N paradas desde el origen minimizando la distancia total.

    Devuelve (orden, tramos): `orden` son los índices de `paradas` en orden de
    visita y `tramos[i]` es el trayecto hasta la parada i del orden, con
    `coords` (polilínea A*) y `distancia_km`.
    """
    puntos = [origen] + paradas
    dist, rutas = _matriz_distancias(puntos)
    orden_global = _mejora_2opt(_vecino_mas_cercano(dist), dist)

    tramos = [
        {"coords": rutas[(a, b)], "distancia_km": dist[a][b]}
        for a, b in zip(orden_global, orden_global[1:])
    ]
    return [idx - 1 for idx in orden_global[1:]], tramos


def calcular_desvio_metros(lat: float, lon: float, ruta: list[tuple[float, float]]) -> float:
    """Distancia en metros desde (lat,lon) al punto más cercano de la ruta."""
    if len(ruta) < 2:
        return 0.0
    min_d = float("inf")
    for i in range(len(ruta) - 1):
        ax, ay = ruta[i]
        bx, by = ruta[i + 1]
        norm2 = (bx - ax) ** 2 + (by - ay) ** 2
        t = (
            max(0.0, min(1.0, ((lat - ax) * (bx - ax) + (lon - ay) * (by - ay)) / norm2))
            if norm2 > 0 else 0.0
        )
        px, py = ax + t * (bx - ax), ay + t * (by - ay)
        min_d = min(min_d, haversine_km(lat, lon, px, py) * 1000)
    return min_d


def calcular_eta_min(distancia_km: float) -> int:
    return max(1, round(distancia_km / _VELOCIDAD_KMH * 60))


# ── Rutas activas en memoria ──────────────────────────────────────────────────

def obtener_ruta_activa(solicitud_id: int) -> list[tuple[float, float]] | None:
    return _rutas_activas.get(solicitud_id)


def guardar_ruta_activa(solicitud_id: int, ruta: list[tuple[float, float]]) -> None:
    _rutas_activas[solicitud_id] = ruta


def limpiar_ruta_activa(solicitud_id: int) -> None:
    _rutas_activas.pop(solicitud_id, None)
    _ubicaciones_activas.pop(solicitud_id, None)


def guardar_ubicacion_activa(
    solicitud_id: int, lat: float, lon: float, eta_min: int | None,
) -> None:
    """Última posición conocida del reciclador, para reenviarla al ciudadano
    que abre la página de seguimiento después del último update GPS."""
    _ubicaciones_activas[solicitud_id] = {"lat": lat, "lon": lon, "eta_min": eta_min}


def obtener_ubicacion_activa(solicitud_id: int) -> dict | None:
    return _ubicaciones_activas.get(solicitud_id)
