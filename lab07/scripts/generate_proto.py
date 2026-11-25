#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,'-m','grpc_tools.protoc','-I'+str(root/'proto'),
                '--python_out='+str(root),'--grpc_python_out='+str(root),
                str(root/'proto/delivery.proto')],check=True)
print('Generated delivery_pb2.py and delivery_pb2_grpc.py')
