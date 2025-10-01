import grpc
from proto import logplugin_pb2, logplugin_pb2_grpc

def send_segment_to_plugin(segment, host, port):
    """
    Отправляет сегмент на плагин и возвращает SegmentResponse.
    """
    channel = grpc.insecure_channel(f"{host}:{port}")
    stub = logplugin_pb2_grpc.PluginServiceStub(channel)

    # Преобразуем сегмент в SegmentRequest
    segment_request = logplugin_pb2.SegmentRequest(
        segment_id=segment["Id"],
        segment_type=segment["Type"],
        start_time=segment["StartTime"] or "",
        end_time=segment["EndTime"] or "",
        logs=[logplugin_pb2.LogEntry(
            level=log.get("level", ""),
            message=log.get("message", ""),
            timestamp=log.get("timestamp", ""),
            module=log.get("module", "")
        ) for log in segment["Logs"]]
    )

    # Вызываем плагин
    response = stub.ProcessSegment(segment_request)
    return response
