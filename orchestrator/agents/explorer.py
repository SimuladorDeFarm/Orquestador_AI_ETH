from agents.base_agent import BaseAgent
from core.runner_client import ejecutar_en_docker



agente = BaseAgent("Eres un experto en Ethical Hacking y te estan preguntando que comando usarías en cada situacion, tienes que responder solo comn el comando como si estuvieras escribiendolo por consola, donde cualquier texto de explicacion daria error, para ejecutar comandos siempre usa tool")

respuesta = agente.preguntar("si tu objetivo es esta ip localhost y tienes que revisar todos los puertos para ver si se quedo uno abierto, que comadno suarias")




""""



comand0 = ejecutar_en_docker("ls")

print(comand0)
"""