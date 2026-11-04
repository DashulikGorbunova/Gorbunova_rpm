"""Run the extracted delivery service as an independent process."""
import logging
from app.core.config import Settings
from delivery_service.server import build_server

def serve():
    logging.basicConfig(level=logging.INFO)
    settings=Settings();server,port=build_server(settings)
    server.start()
    print(f'Delivery gRPC Server running on loopback port {port}',flush=True)
    try:server.wait_for_termination()
    except KeyboardInterrupt:server.stop(2).wait()
if __name__=='__main__':serve()
