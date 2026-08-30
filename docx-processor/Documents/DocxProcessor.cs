using System.Security.Cryptography;
using System.Text;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx.Documents;

internal static class DocxProcessor
{
    public static InspectResponse Inspect(InspectRequest request)
    {
        ValidatePaths(
            [request.SourcePath, request.OutputPath, request.ImageOutputDirectory],
            request.AllowedRoots);
        ValidateDistinctOutputs(request.SourcePath, request.OutputPath);
        ValidateHash(request.SourcePath, request.ExpectedSourceSha256);
        PackageArchivePolicy.Validate(request.SourcePath);

        using (var source = WordprocessingDocument.Open(request.SourcePath, false))
        {
            PackagePolicy.ValidateSource(request.SourcePath, source);
        }

        File.Copy(request.SourcePath, request.OutputPath, true);
        PackageArchivePolicy.Validate(request.OutputPath);
        SanitationSummary sanitation;
        DocxTextBlock[] blocks;
        DocxImageOccurrence[] imageOccurrences;
        using (var output = WordprocessingDocument.Open(request.OutputPath, true))
        {
            PackagePolicy.ValidateSource(request.OutputPath, output);
            sanitation = PrivacySanitizer.Sanitize(output);
            blocks = Blocks(output, request.ExpectedSourceSha256).Select(item => item.Value).ToArray();
            imageOccurrences = ImageProjection.Build(
                output,
                request.ExpectedSourceSha256,
                request.ImageOutputDirectory).Select(item => item.Value).ToArray();
        }

        var documentSha256 = HashFile(request.OutputPath);
        ValidateOutput(request.OutputPath);
        return new InspectResponse(
            blocks.Sum(block => TextProjection.CodePointCount(block.Text)),
            blocks,
            imageOccurrences,
            documentSha256,
            sanitation);
    }

    public static RenderResponse Render(RenderRequest request)
    {
        ValidatePaths(
            [request.SourcePath, request.OutputPath],
            request.AllowedRoots);
        ValidatePaths(
            request.ImageReplacements.Select(item => item.ReplacementPath),
            request.AllowedRoots);
        ValidateDistinctOutputs(request.SourcePath, request.OutputPath);
        ValidateHash(request.SourcePath, request.ExpectedSourceSha256);
        ValidateLayers(request);
        ValidateImageReplacements(request.ImageReplacements);
        PackageArchivePolicy.Validate(request.SourcePath);

        File.Copy(request.SourcePath, request.OutputPath, true);
        PackageArchivePolicy.Validate(request.OutputPath);
        SanitationSummary sanitation;
        using (var output = WordprocessingDocument.Open(request.OutputPath, true))
        {
            PackagePolicy.ValidateSource(request.OutputPath, output);
            sanitation = PrivacySanitizer.Sanitize(output);
            var projected = Blocks(output, request.ExpectedSourceSha256);
            var byId = projected.ToDictionary(item => item.Value.BlockId);

            foreach (var group in request.Layers.GroupBy(layer => layer.Target.BlockId))
            {
                if (!byId.TryGetValue(group.Key, out var block))
                {
                    throw new ProcessorException("invalid_target", "A DOCX target block was not found.");
                }
                foreach (var layer in group.OrderByDescending(item => item.Target.Start))
                {
                    var target = layer.Target;
                    if (target.StoryKind != block.Value.StoryKind
                        || target.PartUri != block.Value.PartUri)
                    {
                        throw new ProcessorException(
                            "invalid_target",
                            "A DOCX target references the wrong document story.");
                    }
                    var current = TextProjection.TextOf(block.Paragraph);
                    if (TextProjection.SliceCodePoints(current, target.Start, target.End) != target.ExactText)
                    {
                        throw new ProcessorException("invalid_target", "A DOCX target no longer matches source text.");
                    }
                    TextProjection.ReplaceRange(
                        block.Paragraph,
                        target.Start,
                        target.End,
                        layer.ReplacementText);
                }
            }
            ImageProjection.ApplyReplacements(
                output,
                request.ExpectedSourceSha256,
                request.ImageReplacements);
            RemoveUnusedHyperlinkRelationships(output);
            SaveStories(output);
        }

        var documentSha256 = HashFile(request.OutputPath);
        ValidateOutput(request.OutputPath);
        return new RenderResponse(
            documentSha256,
            sanitation);
    }

    private static IReadOnlyList<ProjectedBlock> Blocks(
        WordprocessingDocument document,
        string sourceSha256)
    {
        return TextProjection.Build(document, sourceSha256);
    }

    private static void ValidateLayers(RenderRequest request)
    {
        var byBlock = request.Layers.GroupBy(layer => layer.Target.BlockId);
        foreach (var group in byBlock)
        {
            var ordered = group.OrderBy(item => item.Target.Start).ToArray();
            for (var index = 0; index < ordered.Length; index++)
            {
                var layer = ordered[index];
                var target = layer.Target;
                if (target.Format != "docx"
                    || target.SourceSha256 != request.ExpectedSourceSha256
                    || string.IsNullOrWhiteSpace(target.StoryKind)
                    || string.IsNullOrWhiteSpace(target.PartUri)
                    || target.Start < 0
                    || target.End <= target.Start
                    || string.IsNullOrEmpty(target.ExactText))
                {
                    throw new ProcessorException("invalid_target", "A DOCX target is invalid.");
                }
                if (index > 0 && ordered[index - 1].Target.End > target.Start)
                {
                    throw new ProcessorException("overlapping_targets", "DOCX targets cannot overlap.");
                }
                ValidateReplacement(layer.ReplacementText);
            }
        }
    }

    private static void ValidateReplacement(string replacement)
    {
        if (replacement.Length > 512
            || replacement.Any(character => character is '\r' or '\n' or '\t' || char.IsControl(character))
            || replacement.Any(character => !System.Xml.XmlConvert.IsXmlChar(character)))
        {
            throw new ProcessorException("invalid_replacement", "DOCX replacement text is invalid.");
        }
    }

    private static void ValidatePaths(IEnumerable<string> paths, string[] roots)
    {
        var values = paths.ToArray();
        if (roots.Length == 0 || values.Any(path => !IsWithin(path, roots)))
        {
            throw new ProcessorException("unsafe_path", "DOCX paths must stay inside managed roots.");
        }
        foreach (var path in values)
        {
            if (Path.HasExtension(path))
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
            }
            else
            {
                Directory.CreateDirectory(Path.GetFullPath(path));
            }
        }
    }

    private static void ValidateDistinctOutputs(string sourcePath, params string[] outputPaths)
    {
        var paths = outputPaths.Prepend(sourcePath).Select(Path.GetFullPath).ToArray();
        if (paths.Distinct(PathComparer()).Count() != paths.Length)
        {
            throw new ProcessorException("unsafe_path", "The source and DOCX outputs must be distinct.");
        }
    }

    private static bool IsWithin(string path, IEnumerable<string> roots)
    {
        var candidate = Path.GetFullPath(path);
        var comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        return roots.Select(Path.GetFullPath).Any(root =>
            candidate.Equals(root, comparison)
            || candidate.StartsWith(root + Path.DirectorySeparatorChar, comparison));
    }

    private static StringComparer PathComparer() => OperatingSystem.IsWindows()
        ? StringComparer.OrdinalIgnoreCase
        : StringComparer.Ordinal;

    private static void ValidateImageReplacements(IReadOnlyList<DocxImageReplacement> replacements)
    {
        if (replacements.Select(item => item.OccurrenceId).Distinct(StringComparer.Ordinal).Count()
            != replacements.Count)
        {
            throw new ProcessorException("invalid_target", "DOCX picture replacements must be unique.");
        }
        foreach (var replacement in replacements)
        {
            if (!replacement.OccurrenceId.StartsWith("pic_", StringComparison.Ordinal)
                || replacement.OccurrenceId.Length != 68
                || !File.Exists(replacement.ReplacementPath)
                || HashFile(replacement.ReplacementPath) != replacement.ReplacementSha256)
            {
                throw new ProcessorException("invalid_replacement", "A DOCX picture replacement is invalid.");
            }
        }
    }

    private static void ValidateHash(string path, string expected)
    {
        if (!File.Exists(path) || HashFile(path) != expected)
        {
            throw new ProcessorException("source_hash_mismatch", "The DOCX source hash does not match.");
        }
    }

    private static void ValidateOutput(string path)
    {
        PackageArchivePolicy.Validate(path);
        using var document = WordprocessingDocument.Open(path, false);
        PackagePolicy.ValidateSource(path, document);
    }

    private static string HashFile(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    private static void SaveStories(WordprocessingDocument document)
    {
        var main = document.MainDocumentPart
            ?? throw new ProcessorException("invalid_docx", "The DOCX has no main document part.");
        main.Document?.Save();
        foreach (var header in main.HeaderParts)
        {
            header.Header?.Save();
        }
        foreach (var footer in main.FooterParts)
        {
            footer.Footer?.Save();
        }
        main.FootnotesPart?.Footnotes?.Save();
        main.EndnotesPart?.Endnotes?.Save();
    }

    private static void RemoveUnusedHyperlinkRelationships(WordprocessingDocument document)
    {
        var main = document.MainDocumentPart
            ?? throw new ProcessorException("invalid_docx", "The DOCX has no main document part.");
        RemoveUnusedHyperlinkRelationships(main, main.Document);
        foreach (var part in main.HeaderParts)
        {
            RemoveUnusedHyperlinkRelationships(part, part.Header);
        }
        foreach (var part in main.FooterParts)
        {
            RemoveUnusedHyperlinkRelationships(part, part.Footer);
        }
        if (main.FootnotesPart is not null)
        {
            RemoveUnusedHyperlinkRelationships(main.FootnotesPart, main.FootnotesPart.Footnotes);
        }
        if (main.EndnotesPart is not null)
        {
            RemoveUnusedHyperlinkRelationships(main.EndnotesPart, main.EndnotesPart.Endnotes);
        }
    }

    private static void RemoveUnusedHyperlinkRelationships(
        OpenXmlPart part,
        OpenXmlPartRootElement? root)
    {
        if (root is null)
        {
            return;
        }
        var used = root.Descendants<Hyperlink>()
            .Select(item => item.Id?.Value)
            .Where(id => !string.IsNullOrEmpty(id))
            .ToHashSet(StringComparer.Ordinal);
        foreach (var relationship in part.HyperlinkRelationships.ToArray())
        {
            if (!used.Contains(relationship.Id))
            {
                part.DeleteReferenceRelationship(relationship);
            }
        }
    }
}
