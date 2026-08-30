using System.Text.Json;
using System.Text.Json.Serialization;

namespace Aiadr.Docx.Protocol;

internal sealed record RequestEnvelope(
    [property: JsonPropertyName("request_id")] string RequestId,
    [property: JsonPropertyName("operation")] string Operation,
    [property: JsonPropertyName("payload")] JsonElement Payload);

internal sealed record ErrorPayload(
    [property: JsonPropertyName("code")] string Code,
    [property: JsonPropertyName("message")] string Message,
    [property: JsonPropertyName("feature")] string? Feature = null);

internal sealed record ResponseEnvelope(
    [property: JsonPropertyName("request_id")] string RequestId,
    [property: JsonPropertyName("ok")] bool Ok,
    [property: JsonPropertyName("payload")] object? Payload,
    [property: JsonPropertyName("error")] ErrorPayload? Error,
    [property: JsonPropertyName("working_set_bytes")] long WorkingSetBytes);

internal sealed record HandshakeResponse(
    [property: JsonPropertyName("openxml_sdk_version")] string OpenXmlSdkVersion,
    [property: JsonPropertyName("operations")] string[] Operations);

internal sealed record InspectRequest(
    [property: JsonPropertyName("source_path")] string SourcePath,
    [property: JsonPropertyName("expected_source_sha256")] string ExpectedSourceSha256,
    [property: JsonPropertyName("output_path")] string OutputPath,
    [property: JsonPropertyName("image_output_directory")] string ImageOutputDirectory,
    [property: JsonPropertyName("allowed_roots")] string[] AllowedRoots);

internal sealed record RenderRequest(
    [property: JsonPropertyName("source_path")] string SourcePath,
    [property: JsonPropertyName("expected_source_sha256")] string ExpectedSourceSha256,
    [property: JsonPropertyName("output_path")] string OutputPath,
    [property: JsonPropertyName("layers")] DocxRenderLayer[] Layers,
    [property: JsonPropertyName("image_replacements")] DocxImageReplacement[] ImageReplacements,
    [property: JsonPropertyName("allowed_roots")] string[] AllowedRoots);

internal sealed record DocxRenderLayer(
    [property: JsonPropertyName("layer_id")] string LayerId,
    [property: JsonPropertyName("target")] DocxTextLocator Target,
    [property: JsonPropertyName("replacement_text")] string ReplacementText);

internal sealed record DocxTextLocator(
    [property: JsonPropertyName("format")] string Format,
    [property: JsonPropertyName("page")] int Page,
    [property: JsonPropertyName("line_id")] string LineId,
    [property: JsonPropertyName("source_sha256")] string SourceSha256,
    [property: JsonPropertyName("story_kind")] string StoryKind,
    [property: JsonPropertyName("part_uri")] string PartUri,
    [property: JsonPropertyName("block_id")] string BlockId,
    [property: JsonPropertyName("start")] int Start,
    [property: JsonPropertyName("end")] int End,
    [property: JsonPropertyName("exact_text")] string ExactText);

internal sealed record DocxTextBlock(
    [property: JsonPropertyName("block_id")] string BlockId,
    [property: JsonPropertyName("ordinal")] int Ordinal,
    [property: JsonPropertyName("story_kind")] string StoryKind,
    [property: JsonPropertyName("part_uri")] string PartUri,
    [property: JsonPropertyName("structural_path")] string StructuralPath,
    [property: JsonPropertyName("text")] string Text);

internal sealed record DocxImageOccurrence(
    [property: JsonPropertyName("id")] string Id,
    [property: JsonPropertyName("ordinal")] int Ordinal,
    [property: JsonPropertyName("story_kind")] string StoryKind,
    [property: JsonPropertyName("part_uri")] string PartUri,
    [property: JsonPropertyName("media_type")] string MediaType,
    [property: JsonPropertyName("source_asset")] string? SourceAsset,
    [property: JsonPropertyName("crop_left")] int CropLeft,
    [property: JsonPropertyName("crop_top")] int CropTop,
    [property: JsonPropertyName("crop_right")] int CropRight,
    [property: JsonPropertyName("crop_bottom")] int CropBottom,
    [property: JsonPropertyName("flip_horizontal")] bool FlipHorizontal,
    [property: JsonPropertyName("flip_vertical")] bool FlipVertical,
    [property: JsonPropertyName("targetable")] bool Targetable,
    [property: JsonPropertyName("unsupported_reason")] string? UnsupportedReason);

internal sealed record DocxImageReplacement(
    [property: JsonPropertyName("occurrence_id")] string OccurrenceId,
    [property: JsonPropertyName("replacement_path")] string ReplacementPath,
    [property: JsonPropertyName("replacement_sha256")] string ReplacementSha256);

internal sealed record SanitationSummary(
    [property: JsonPropertyName("comments_removed")] int CommentsRemoved,
    [property: JsonPropertyName("properties_removed")] int PropertiesRemoved);

internal sealed record InspectResponse(
    [property: JsonPropertyName("character_count")] int CharacterCount,
    [property: JsonPropertyName("blocks")] DocxTextBlock[] Blocks,
    [property: JsonPropertyName("image_occurrences")] DocxImageOccurrence[] ImageOccurrences,
    [property: JsonPropertyName("document_sha256")] string DocumentSha256,
    [property: JsonPropertyName("sanitation")] SanitationSummary Sanitation);

internal sealed record RenderResponse(
    [property: JsonPropertyName("document_sha256")] string DocumentSha256,
    [property: JsonPropertyName("sanitation")] SanitationSummary Sanitation);

internal sealed class ProcessorException(string code, string message, string? feature = null)
    : Exception(message)
{
    public string Code { get; } = code;
    public string? Feature { get; } = feature;
}
