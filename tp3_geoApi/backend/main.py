import os
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import redis

# Datos semilla para Concepción del Uruguay, Entre Ríos
SEED_POIS = {
    "cervecerias": [
        ("Cervecería 7 Colinas", -58.2485, -32.4802),
        ("Drakkar Bodega Cervecera", -58.2274, -32.4831),
        ("Biguá Cervecería", -58.2350, -32.4850)
    ],
    "universidades": [
        ("Universidad de Concepción del Uruguay (UCU)", -58.22971, -32.48148),
        ("UTN - Facultad Regional Concepción del Uruguay", -58.22972, -32.49556),
        ("UNER - Facultad de Ciencias de la Salud", -58.2605, -32.4795)
    ],
    "farmacias": [
        ("Farmacia Maffioly", -58.2450, -32.4785),
        ("Farmacia Pasteur", -58.2310, -32.4810),
        ("Farmacia Central", -58.2405, -32.4795),
        ("Farmacia del Pueblo", -58.2420, -32.4820)
    ],
    "emergencias": [
        ("Hospital Justo José de Urquiza", -58.2610, -32.48144),
        ("Clínica Uruguay", -58.2325, -32.4837),
        ("Cooperativa Médica (CEMUR)", -58.2425, -32.4805)
    ],
    "supermercados": [
        ("Supermercado Gran Rex (Perón 330)", -58.230312, -32.4891967),
        ("Supermercado DIA (Sarmiento 1552)", -58.2512, -32.4835),
        ("Supermercado Gran Rex (Posadas 414)", -58.2365, -32.4818)
    ]
}

def seed_db():
    try:
        for category, items in SEED_POIS.items():
            key = f"poi:{category}"
            for name, lon, lat in items:
                r.geoadd(key, (lon, lat, name))
        print("Base de datos sembrada con éxito.")
    except Exception as e:
        print(f"Error al sembrar la base de datos: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sembrar datos al inicio
    seed_db()
    yield

# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="API de Turismo con Geo Redis",
    description="API para gestionar y buscar puntos de interés (POIs) usando capacidades geoespaciales de Redis.",
    version="1.0.0",
    lifespan=lifespan
)

# Configuración de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de la conexión a Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))

try:
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        decode_responses=True # Convierte las respuestas de bytes a strings de Python
    )
except Exception as e:
    print(f"Error al conectar con Redis: {e}")

# Grupos de interés / Categorías permitidas
CATEGORIES = {
    "cervecerias": "Cervecerías artesanales",
    "universidades": "Universidades",
    "farmacias": "Farmacias",
    "emergencias": "Centros de atención de emergencias",
    "supermercados": "Supermercados"
}

# Esquemas de datos (Pydantic)
class POICreate(BaseModel):
    category: str = Field(..., description="Categoría del punto de interés")
    name: str = Field(..., min_length=2, max_length=100, description="Nombre del punto de interés")
    latitude: float = Field(..., description="Latitud (-90 a 90)")
    longitude: float = Field(..., description="Longitud (-180 a 180)")

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"Categoría inválida. Debe ser una de: {list(CATEGORIES.keys())}")
        return value

    @field_validator("latitude")
    @classmethod
    def validate_latitude(cls, value: float) -> float:
        if not (-90.0 <= value <= 90.0):
            raise ValueError("La latitud debe estar entre -90.0 y 90.0 grados.")
        return value

    @field_validator("longitude")
    @classmethod
    def validate_longitude(cls, value: float) -> float:
        if not (-180.0 <= value <= 180.0):
            raise ValueError("La longitud debe estar entre -180.0 y 180.0 grados.")
        return value

class POIResponse(BaseModel):
    category: str
    category_label: str
    name: str
    latitude: float
    longitude: float
    distance_meters: Optional[float] = None

class DistanceResponse(BaseModel):
    category: str
    name: str
    user_latitude: float
    user_longitude: float
    distance_meters: float

@app.get("/api/poi/categories", tags=["Configuración"])
def get_categories():
    """Retorna la lista de categorías soportadas con sus etiquetas descriptivas."""
    return [{"id": k, "name": v} for k, v in CATEGORIES.items()]

@app.post("/api/poi", response_model=POIResponse, status_code=status.HTTP_201_CREATED, tags=["Puntos de Interés"])
def create_poi(poi: POICreate):
    """
    Agrega un nuevo punto de interés (POI) en Redis.
    
    Internamente utiliza el comando **GEOADD** para registrar las coordenadas.
    """
    key = f"poi:{poi.category}"
    try:
        # En redis-py, geoadd recibe el formato: geoadd(key, (longitude, latitude, member))
        # Retorna el número de elementos agregados (o actualizados)
        r.geoadd(key, (poi.longitude, poi.latitude, poi.name))
        
        return POIResponse(
            category=poi.category,
            category_label=CATEGORIES[poi.category],
            name=poi.name,
            latitude=poi.latitude,
            longitude=poi.longitude
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al guardar en base de datos: {str(e)}"
        )

@app.get("/api/poi/search", response_model=List[POIResponse], tags=["Puntos de Interés"])
def search_pois(
    lat: float = Query(..., description="Latitud del usuario"),
    lon: float = Query(..., description="Longitud del usuario"),
    radius_km: float = Query(5.0, description="Radio de búsqueda en kilómetros (por defecto 5 km)"),
    category: Optional[str] = Query(None, description="Filtrar por una categoría específica. Si se omite, busca en todas.")
):
    """
    Busca puntos de interés dentro de un radio de X kilómetros en base a la ubicación del usuario.
    
    Internamente utiliza el comando **GEOSEARCH** con la opción **BYRADIUS**.
    """
    # Validar coordenadas de entrada
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Coordenadas de usuario inválidas."
        )

    # Determinar qué categorías buscar
    categories_to_search = [category] if category else list(CATEGORIES.keys())
    results = []

    for cat in categories_to_search:
        if cat not in CATEGORIES:
            continue
        
        key = f"poi:{cat}"
        try:
            # GEOSEARCH key FROMLONLAT lon lat BYRADIUS radius km WITHDIST WITHCOORD
            # En redis-py esto se traduce a geosearch con flags correspondientes.
            # Nota: Si la clave no existe en Redis, retorna una lista vacía.
            raw_results = r.geosearch(
                name=key,
                longitude=lon,
                latitude=lat,
                radius=radius_km,
                unit="km",
                withdist=True,
                withcoord=True
            )
            
            # Formatear resultados
            for item in raw_results:
                # El formato devuelto por redis-py es: [member, distance, (longitude, latitude)]
                member_name = item[0]
                dist_km = item[1]
                coord = item[2] # (longitude, latitude)
                
                results.append(POIResponse(
                    category=cat,
                    category_label=CATEGORIES[cat],
                    name=member_name,
                    latitude=coord[1],
                    longitude=coord[0],
                    distance_meters=dist_km * 1000.0  # Convertir a metros para mayor precisión en la visualización
                ))
        except Exception as e:
            # Ignorar o reportar error en una categoría específica para no romper toda la consulta
            print(f"Error buscando en la categoría '{cat}': {e}")
            continue

    # Ordenar por distancia de menor a mayor
    results.sort(key=lambda x: x.distance_meters if x.distance_meters is not None else float('inf'))
    return results

@app.get("/api/poi/distance", response_model=DistanceResponse, tags=["Puntos de Interés"])
def get_poi_distance(
    lat: float = Query(..., description="Latitud del usuario"),
    lon: float = Query(..., description="Longitud del usuario"),
    category: str = Query(..., description="Categoría del punto de interés"),
    name: str = Query(..., description="Nombre exacto del punto de interés")
):
    """
    Calcula la distancia exacta entre el usuario y un punto de interés específico de una categoría.
    
    Utiliza de forma nativa los comandos **GEOADD**, **GEODIST** y **ZREM** en Redis.
    """
    if category not in CATEGORIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Categoría inválida. Debe ser una de: {list(CATEGORIES.keys())}"
        )

    key = f"poi:{category}"
    temp_user_id = f"temp_user:{uuid.uuid4()}"

    try:
        # 1. Agregar temporalmente la ubicación del usuario al sorted set de la categoría
        # GEOADD key lon lat temp_user_id
        r.geoadd(key, (lon, lat, temp_user_id))

        # 2. Calcular la distancia entre el usuario temporal y el POI
        # GEODIST key temp_user_id name m
        dist_m = r.geodist(key, temp_user_id, name, unit="m")

        # 3. Remover el usuario temporal de Redis
        # ZREM key temp_user_id
        r.zrem(key, temp_user_id)

        # Si el punto de interés no existe, dist_m será None
        if dist_m is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El punto de interés '{name}' no fue encontrado en la categoría '{category}'."
            )

        return DistanceResponse(
            category=category,
            name=name,
            user_latitude=lat,
            user_longitude=lon,
            distance_meters=float(dist_m)
        )
    except HTTPException:
        raise
    except Exception as e:
        # Asegurar limpieza en caso de error
        try:
            r.zrem(key, temp_user_id)
        except:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error en el servidor al calcular la distancia: {str(e)}"
        )

@app.get("/health", tags=["Salud"])
def health_check():
    """Verifica el estado del servicio de backend y la conexión a Redis."""
    try:
        redis_ready = r.ping()
        return {
            "status": "online",
            "redis_connected": redis_ready
        }
    except Exception as e:
        return {
            "status": "degraded",
            "redis_connected": False,
            "error": str(e)
        }
