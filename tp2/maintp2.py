from redis import Redis
from flask import Flask, jsonify, request

r = Redis(host='localhost', port=6379, decode_responses=True)

app = Flask(__name__)

@app.route('/')

def inicio():
    try:
        if r.ping():
            return "<h1>¡La arquitectura funciona!</h1><p>Flask está escuchando y Redis responde perfecto.</p>"
    except Exception as e:
        return f"<h1>Error de base de datos</h1><p>Flask está andando, pero Redis no responde: {e}</p>"



#s1e1,s1e2 etc representan el id con el cual se identifica cada capitulo
def cargar_temporada_1():
    #veo si ya existe la lista
    if r.exists('catalogo_1') == 0:
        
        r.rpush('catalogo_1',
                's1e1|Temporada 1 - Capitulo 1: El Mandaloriano',
                's1e2|Temporada 1 - Capitulo 2: El Niño',
                's1e3|Temporada 1 - Capitulo 3: El Pecado',
                's1e4|Temporada 1 - Capitulo 4: Santuario',
                's1e5|Temporada 1 - Capitulo 5: El Pistolero',
                's1e6|Temporada 1 - Capitulo 6: El Prisionero',
                's1e7|Temporada 1 - Captulo 7: El Ajuste de Cuentas',
                's1e8|Temporada 1 - Capitulo 8: Redención'
        )
        print("Temporada 1 cargada")
    else:
        print("El catalogo ya estaba en la memoria.")

cargar_temporada_1()

def cargar_temporada_2():
    if (r.exists('catalogo_2')) == 0:
        r.rpush('catalogo_2',
                's2e1|Temporada 2 - Capítulo 1: El Marshal',
                's2e2|Temporada 2 - Capítulo 2: El Pasajero',
                's2e3|Temporada 2 - Capítulo 3: La Heredera',
                's2e4|Temporada 2 - Capítulo 4: El Asedio',
                's2e5|Temporada 2 - Capítulo 5: La Jedi',
                's2e6|Temporada 2 - Capítulo 6: La Tragedia',
                's2e7|Temporada 2 - Capítulo 7: El Creyente',
                's2e8|Temporada 2 - Capítulo 8: El Rescate')
        print("Temporada 2 cargada")
    else: 
        print('ya estaba cargada')

cargar_temporada_2()

def cargar_temporada_3():
    if r.exists('catalogo_3') == 0:
        r.rpush('catalogo_3',
                's3e1|Temporada 3 - Capítulo 1: El Apóstata',
                's3e2|Temporada 3 - Capítulo 2: Las Minas de Mandalore',
                's3e3|Temporada 3 - Capítulo 3: El Converso',
                's3e4|Temporada 3 - Capítulo 4: El Huérfano',
                's3e5|Temporada 3 - Capítulo 5: El Pirata',
                's3e6|Temporada 3 - Capítulo 6: Armas de Alquiler',
                's3e7|Temporada 3 - Capítulo 7: El Espía',
                's3e8|Temporada 3 - Capítulo 8: El Retorno')
        print("¡Temporada 3 cargada!")
    else: 
        print('La temporada 3 ya estaba cargada')

cargar_temporada_3()

#----------------------------------------------------------------------------------

#FUNCION NUEVA Q LISTA LOS CAPITULOS YA Q LA MIA NO HACE ESO
@app.route('/capitulos')
def listar_capitulos():
    resultado = [] #lista para guardar los datos del cap
    for catalogo in ['catalogo_1', 'catalogo_2', 'catalogo_3']:
        for item in r.lrange(catalogo, 0, -1): #item= lo q devuelve redis de la lista de caps
            ep_id, titulo = item.split('|', 1) #corta el string en 2 '|', tomando c/u como variable
            if r.exists(f"alquiler:{ep_id}"):  
                estado = "alquilado"
            elif r.exists(f"reserva:{ep_id}"):
                estado = "reservado"
            else:
                estado = "disponible"
            resultado.append({"id": ep_id, "titulo": titulo, "estado": estado})
    return jsonify(resultado)


#ejecuta la funcion si recibe un paquete pidiendo entrar a la ruta /reservar
@app.route('/reservar/<id_capitulo>') 
#<id_capitulo> var dinamica, guarda lo q se escribe en id_capitulo 

def reservar(id_capitulo):
    # 1. Control de disponibilidad

    if  r.exists(f"reserva:{id_capitulo}"):
        r.exists(f"alquiler:{id_capitulo}")
        return "Este capitulo se encuentra reservado u alquilado por otra persona"

    # 2.estado de RESERVA temporal 
    r.setex(f"reserva:{id_capitulo}", 15, "esperando_pago")
    
    return f"Reservaste el capitulo {id_capitulo}. Tenes 4 minutos para pagar."

#---------------------------------------------------------------------------------------

@app.route('/confirma_pago/<id_capitulo>/<precio>') 


def confirma_pago(id_capitulo,precio):
    confirmacion = input(f"¿Desea confirmar el pago del capitulo {id_capitulo} por ${precio}? (s/n): ")
                         
    if confirmacion == 's':
    
    #mira si el setex no expiro                #mira q no este alquilado previamente
        if r.exists(f"reserva:{id_capitulo}") and not r.exists(f"alquiler:{id_capitulo}"):
            r.delete(f"reserva:{id_capitulo}") 
            r.setex(f"alquiler:{id_capitulo}",20,f"pagado|precio:{precio}")

            return f"Pago confirmado. Capitulo {id_capitulo} alquilado por 24hs"
        else:
            return "La reserva expiro o no existe"
    
    else:
        return ("pago cancelado")


if __name__ == '__main__':
    app.run(debug=True, port=5000) 