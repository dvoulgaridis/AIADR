using System.Buffers.Binary;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Aiadr.Docx.Protocol;

internal static class Framing
{
    private const int MaxFrameBytes = 16 * 1024 * 1024;

    public static async Task<RequestEnvelope?> ReadAsync(Stream input, CancellationToken token)
    {
        var header = new byte[4];
        var read = await ReadExactlyOrEofAsync(input, header, token);
        if (!read)
        {
            return null;
        }

        var length = BinaryPrimitives.ReadUInt32BigEndian(header);
        if (length is 0 or > MaxFrameBytes)
        {
            throw new ProcessorException("protocol_error", "Invalid request frame size.");
        }

        var payload = new byte[length];
        await input.ReadExactlyAsync(payload, token);
        return JsonSerializer.Deserialize<RequestEnvelope>(payload, JsonOptions.Default)
            ?? throw new ProcessorException("protocol_error", "Request frame is empty.");
    }

    public static async Task WriteAsync(Stream output, ResponseEnvelope response, CancellationToken token)
    {
        var payload = JsonSerializer.SerializeToUtf8Bytes(response, JsonOptions.Default);
        if (payload.Length > MaxFrameBytes)
        {
            throw new ProcessorException("protocol_error", "Response frame exceeds the limit.");
        }

        var header = new byte[4];
        BinaryPrimitives.WriteUInt32BigEndian(header, (uint)payload.Length);
        await output.WriteAsync(header, token);
        await output.WriteAsync(payload, token);
        await output.FlushAsync(token);
    }

    private static async Task<bool> ReadExactlyOrEofAsync(
        Stream input,
        Memory<byte> buffer,
        CancellationToken token)
    {
        var offset = 0;
        while (offset < buffer.Length)
        {
            var read = await input.ReadAsync(buffer[offset..], token);
            if (read == 0)
            {
                return offset == 0
                    ? false
                    : throw new EndOfStreamException("Truncated request frame.");
            }
            offset += read;
        }
        return true;
    }
}

internal static class JsonOptions
{
    public static readonly JsonSerializerOptions Default = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
    };
}
