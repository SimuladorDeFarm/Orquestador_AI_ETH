import subprocess


NOMBRE_CONTENEDOR = "dazzling_mayer"

def ejecutar_en_docker(comando):
    print("Ejecutando comando")
    cmd = ["docker", "exec", NOMBRE_CONTENEDOR] + comando.split()
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode == 0:
        print("Docker ejecutandose")
        return resultado.stdout
    else:
        return resultado.stderr
