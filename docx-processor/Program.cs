using System.Diagnostics;
using System.Reflection;
using System.Text.Json;
using DocumentFormat.OpenXml;
using Aiadr.Docx.Documents;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx;

internal static class Program
{
    public static async Task<int> Main(string[] args)
    {
        try
        {
            if (args is ["host", "--stdio"])
            {
                await RunHostAsync(CancellationToken.None);
                return 0;
            }
            if (args is ["inspect" or "render", "--request", var path])
            {
                var request = JsonSerializer.Deserialize<RequestEnvelope>(
                    await File.ReadAllBytesAsync(path),
                    JsonOptions.Default)
                    ?? throw new ProcessorException("protocol_error", "Request is empty.");
                var response = Execute(request);
                await Console.OpenStandardOutput().WriteAsync(
                    JsonSerializer.SerializeToUtf8Bytes(response, JsonOptions.Default));
                return response.Ok ? 0 : 2;
            }
            Console.Error.WriteLine("Usage: aiadr-docx host --stdio | <inspect|render> --request FILE");
            return 2;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(error.Message);
            return 2;
        }
    }

    private static async Task RunHostAsync(CancellationToken token)
    {
        var input = Console.OpenStandardInput();
        var output = Console.OpenStandardOutput();
        while (await Framing.ReadAsync(input, token) is { } request)
        {
            await Framing.WriteAsync(output, Execute(request), token);
        }
    }

    private static ResponseEnvelope Execute(RequestEnvelope request)
    {
        try
        {
            object payload = request.Operation switch
            {
                "handshake" => new HandshakeResponse(
                    typeof(OpenXmlElement).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion
                        ?? typeof(OpenXmlElement).Assembly.GetName().Version?.ToString()
                        ?? "unknown",
                    ["inspect", "render"]),
                "inspect" => DocxProcessor.Inspect(
                    request.Payload.Deserialize<InspectRequest>(JsonOptions.Default)
                    ?? throw new ProcessorException("protocol_error", "Missing inspect payload.")),
                "render" => DocxProcessor.Render(
                    request.Payload.Deserialize<RenderRequest>(JsonOptions.Default)
                    ?? throw new ProcessorException("protocol_error", "Missing render payload.")),
                _ => throw new ProcessorException("protocol_error", "Unsupported operation."),
            };
            return new ResponseEnvelope(
                request.RequestId,
                true,
                payload,
                null,
                Process.GetCurrentProcess().WorkingSet64);
        }
        catch (ProcessorException error)
        {
            return new ResponseEnvelope(
                request.RequestId,
                false,
                null,
                new ErrorPayload(error.Code, error.Message, error.Feature),
                Process.GetCurrentProcess().WorkingSet64);
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"processor_failure type={error.GetType().Name}");
            return new ResponseEnvelope(
                request.RequestId,
                false,
                null,
                new ErrorPayload("processor_failure", "DOCX processing failed."),
                Process.GetCurrentProcess().WorkingSet64);
        }
    }
}
