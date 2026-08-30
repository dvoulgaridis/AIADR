using System.Security.Cryptography;
using System.Text;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx.Documents;

internal sealed record ProjectedPicture(
    DocxImageOccurrence Value,
    DocumentStory Story,
    Drawing Drawing,
    A.Blip? Blip,
    PIC.BlipFill? BlipFill,
    A.Transform2D? Transform);

internal static class ImageProjection
{
    private static readonly HashSet<string> SupportedMediaTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/bmp",
        "image/tiff",
    };

    public static IReadOnlyList<ProjectedPicture> Build(
        WordprocessingDocument document,
        string sourceSha256,
        string? assetDirectory = null)
    {
        if (assetDirectory is not null)
        {
            Directory.CreateDirectory(assetDirectory);
        }

        var result = new List<ProjectedPicture>();
        foreach (var story in OpenXmlTraversal.Stories(document))
        {
            foreach (var drawing in story.Root.Descendants<Drawing>())
            {
                var pictures = drawing.Descendants<PIC.Picture>().ToArray();
                if (pictures.Length == 0 && !drawing.Descendants<A.Blip>().Any())
                {
                    continue;
                }
                var picture = pictures.Length == 1 ? pictures[0] : null;
                PIC.BlipFill[] blipFills = picture is null
                    ? []
                    : picture.Elements<PIC.BlipFill>().ToArray();
                var blipFill = blipFills.Length == 1 ? blipFills[0] : null;
                A.Blip[] blips = blipFill is null
                    ? []
                    : blipFill.Elements<A.Blip>().ToArray();
                var blip = blips.Length == 1 ? blips[0] : null;
                PIC.ShapeProperties[] shapeProperties = picture is null
                    ? []
                    : picture.Elements<PIC.ShapeProperties>().ToArray();
                A.Transform2D[] transforms = shapeProperties.Length == 1
                    ? shapeProperties[0].Elements<A.Transform2D>().ToArray()
                    : [];
                var transform = transforms.Length == 1 ? transforms[0] : null;
                var path = OpenXmlTraversal.StructuralPath(drawing, story.Root);
                var occurrenceId = OccurrenceId(sourceSha256, story, path);
                var unsupportedReason = UnsupportedReason(
                    drawing,
                    pictures.Length,
                    blipFills.Length,
                    blips.Length,
                    shapeProperties.Length,
                    transforms.Length,
                    blip);
                ImagePart? imagePart = null;
                var mediaType = "application/octet-stream";

                if (unsupportedReason is null && blip?.Embed?.Value is { Length: > 0 } relationshipId)
                {
                    try
                    {
                        imagePart = story.Part.GetPartById(relationshipId) as ImagePart;
                    }
                    catch (ArgumentOutOfRangeException)
                    {
                        unsupportedReason = "missing_image_relationship";
                    }
                    if (imagePart is null && unsupportedReason is null)
                    {
                        unsupportedReason = "relationship_is_not_an_image";
                    }
                }

                if (imagePart is not null)
                {
                    mediaType = imagePart.ContentType;
                    if (!SupportedMediaTypes.Contains(mediaType))
                    {
                        unsupportedReason = "unsupported_image_format";
                    }
                }

                string? sourceAsset = null;
                if (unsupportedReason is null && imagePart is not null && assetDirectory is not null)
                {
                    sourceAsset = occurrenceId + ExtensionFor(mediaType);
                    var target = Path.Combine(assetDirectory, sourceAsset);
                    using var input = imagePart.GetStream(FileMode.Open, FileAccess.Read);
                    using var output = new FileStream(target, FileMode.Create, FileAccess.Write, FileShare.None);
                    input.CopyTo(output);
                }

                var sourceRectangle = blipFill?.SourceRectangle;
                var value = new DocxImageOccurrence(
                    occurrenceId,
                    result.Count,
                    story.Kind,
                    story.PartUri,
                    mediaType,
                    sourceAsset,
                    CropValue(sourceRectangle?.Left),
                    CropValue(sourceRectangle?.Top),
                    CropValue(sourceRectangle?.Right),
                    CropValue(sourceRectangle?.Bottom),
                    transform?.HorizontalFlip?.Value ?? false,
                    transform?.VerticalFlip?.Value ?? false,
                    unsupportedReason is null,
                    unsupportedReason);
                result.Add(new ProjectedPicture(value, story, drawing, blip, blipFill, transform));
            }
        }
        return result;
    }

    public static void ApplyReplacements(
        WordprocessingDocument document,
        string sourceSha256,
        IReadOnlyList<DocxImageReplacement> replacements)
    {
        if (replacements.Count == 0)
        {
            return;
        }
        var projected = Build(document, sourceSha256).ToDictionary(item => item.Value.Id);
        foreach (var replacement in replacements.OrderBy(item => item.OccurrenceId, StringComparer.Ordinal))
        {
            if (!projected.TryGetValue(replacement.OccurrenceId, out var occurrence)
                || !occurrence.Value.Targetable
                || occurrence.Blip is null
                || occurrence.BlipFill is null)
            {
                throw new ProcessorException("invalid_target", "A DOCX picture occurrence was not found.");
            }

            var imagePart = occurrence.Story.Part.AddNewPart<ImagePart>("image/png");
            using (var source = File.OpenRead(replacement.ReplacementPath))
            {
                imagePart.FeedData(source);
            }
            occurrence.Blip.Embed = occurrence.Story.Part.GetIdOfPart(imagePart);
            occurrence.Blip.Link = null;
            occurrence.BlipFill.SourceRectangle?.Remove();
            if (occurrence.Transform is { } transform)
            {
                transform.HorizontalFlip = null;
                transform.VerticalFlip = null;
            }
        }
    }

    private static string? UnsupportedReason(
        Drawing drawing,
        int pictureCount,
        int blipFillCount,
        int blipCount,
        int shapePropertiesCount,
        int transformCount,
        A.Blip? blip)
    {
        if (pictureCount == 0)
        {
            return "unsupported_drawing_type";
        }
        if (pictureCount > 1 || shapePropertiesCount != 1 || transformCount > 1)
        {
            return "unsupported_picture_container";
        }
        if (blipFillCount != 1 || blipCount != 1 || blip is null)
        {
            return "unsupported_drawing_type";
        }
        if (blip.Link?.Value is { Length: > 0 })
        {
            return "external_image";
        }
        if (string.IsNullOrWhiteSpace(blip.Embed?.Value))
        {
            return "missing_image_relationship";
        }
        if (drawing.Descendants<DW.DocProperties>().Count() != 1)
        {
            return "unsupported_picture_container";
        }
        return null;
    }

    private static int CropValue(Int32Value? value) => Math.Clamp(value?.Value ?? 0, 0, 100000);

    private static string ExtensionFor(string mediaType) => mediaType.ToLowerInvariant() switch
    {
        "image/png" => ".png",
        "image/jpeg" => ".jpg",
        "image/gif" => ".gif",
        "image/bmp" => ".bmp",
        "image/tiff" => ".tiff",
        _ => ".bin",
    };

    private static string OccurrenceId(
        string sourceSha256,
        DocumentStory story,
        string structuralPath)
    {
        var material = string.Join(
            '\0',
            sourceSha256,
            story.PartUri,
            story.Kind,
            structuralPath);
        return "pic_" + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(material)));
    }
}
