# plugins/example_plugin.py

import sys
import os
# Добавляем папку proto в путь поиска модулей
proto_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'proto'))
if proto_path not in sys.path:
    sys.path.insert(0, proto_path)

import grpc
from concurrent import futures
import time

from proto import logplugin_pb2
from proto import logplugin_pb2_grpc

class ExamplePlugin(logplugin_pb2_grpc.PluginServiceServicer):
    def ProcessSegment(self, request, context):
        # request — SegmentRequest
        # Возвращаем сегмент с только ошибочными логами
        error_logs = [
            logplugin_pb2.LogEntry(
                level=log.level,
                message=log.message,
                timestamp=log.timestamp,
                module=log.module
            )
            for log in request.logs
            if log.level.lower() == "error"
        ]
        return logplugin_pb2.SegmentResponse(
            success=True,
            message=f"Found {len(error_logs)} errors",
            logs=error_logs,
            metadata={"plugin": "example_plugin"}
        )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    logplugin_pb2_grpc.add_PluginServiceServicer_to_server(ExamplePlugin(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("Plugin server running on port 50051...")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)

if __name__ == "__main__":
    serve()
