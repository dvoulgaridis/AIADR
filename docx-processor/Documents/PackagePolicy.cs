using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx.Documents;

internal static class PackagePolicy
{
    private const long MaxSourceBytes = 50L * 1024 * 1024;

    public static void ValidateSource(string path, WordprocessingDocument document)
    {
        if (new FileInfo(path).Length > MaxSourceBytes)
        {
            throw Unsupported("package_limit", "The DOCX exceeds the supported package size.");
        }
        if (document.DocumentType != WordprocessingDocumentType.Document)
        {
            throw Unsupported("document_type", "Only ordinary DOCX documents are supported.");
        }

        var main = document.MainDocumentPart
            ?? throw Unsupported("main_document", "The DOCX has no main document part.");
        var documentRoot = main.Document
            ?? throw Unsupported("main_document", "The DOCX has no main document part.");
        _ = documentRoot.Body
            ?? throw Unsupported("main_document", "The DOCX has no document body.");

        if (EnumerateParts(document).Any(part => part.ExternalRelationships.Any()))
        {
            throw Unsupported(
                "external_relationship",
                "Externally loaded package content is not supported.");
        }

        RejectActiveParts(document);
    }

    private static void RejectActiveParts(WordprocessingDocument document)
    {
        var rejected = new HashSet<string>(StringComparer.Ordinal)
        {
            "ActiveXPart",
            "AlternativeFormatImportPart",
            "EmbeddedControlPersistenceBinaryDataPart",
            "EmbeddedControlPersistencePart",
            "EmbeddedObjectPart",
            "EmbeddedPackagePart",
            "VbaDataPart",
            "VbaProjectPart",
        };

        foreach (var part in EnumerateParts(document))
        {
            if (rejected.Contains(part.GetType().Name))
            {
                throw Unsupported(
                    "active_content",
                    $"The DOCX contains active or embedded content ({part.GetType().Name}).");
            }
        }
    }

    private static IEnumerable<OpenXmlPart> EnumerateParts(OpenXmlPackage package)
    {
        var seen = new HashSet<Uri>();
        var pending = new Stack<OpenXmlPart>(package.Parts.Select(item => item.OpenXmlPart));
        while (pending.TryPop(out var part))
        {
            if (!seen.Add(part.Uri))
            {
                continue;
            }
            yield return part;
            foreach (var child in part.Parts)
            {
                pending.Push(child.OpenXmlPart);
            }
        }
    }

    private static ProcessorException Unsupported(string feature, string message) =>
        new("unsupported_docx_feature", message, feature);
}
