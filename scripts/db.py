"""Local educational adapter: psql inside a dedicated Docker PostgreSQL."""
import os
import subprocess

def sql(query):
    return subprocess.check_output(
        ['docker','--host=unix:///var/run/docker.sock','exec','-i',
         os.getenv('PG_CONTAINER','rpm-lab-postgres'),'psql','-X','-qAt',
         '-v','ON_ERROR_STOP=1','-U','postgres'],
        input=query,text=True).strip()
