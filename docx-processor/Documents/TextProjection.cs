using System.Security.Cryptography;
using System.Text;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx.Documents;

internal sealed record ProjectedBlock(DocxTextBlock Value, Paragraph Paragraph);

internal static class TextProjection
{
    public static IReadOnlyList<ProjectedBlock> Build(
        WordprocessingDocument document,
        string sourceSha256)
    {
        var result = new List<ProjectedBlock>();
        foreach (var story in OpenXmlTraversal.Stories(document))
        {
            foreach (var paragraph in Paragraphs(story.Root))
            {
                var text = TextOf(paragraph);
                var path = OpenXmlTraversal.StructuralPath(paragraph, story.Root);
                var blockId = BlockId(sourceSha256, story.Kind, story.PartUri, path);
                result.Add(
                    new ProjectedBlock(
                        new DocxTextBlock(
                            blockId,
                            result.Count,
                            story.Kind,
                            story.PartUri,
                            path,
                            text),
                        paragraph));
            }
        }
        return result;
    }

    public static string TextOf(Paragraph paragraph)
    {
        var builder = new StringBuilder();
        foreach (var leaf in paragraph.Descendants<OpenXmlLeafElement>())
        {
            if (leaf.Ancestors<Paragraph>().FirstOrDefault() != paragraph)
            {
                continue;
            }
            switch (leaf)
            {
                case Text text:
                    builder.Append(text.Text);
                    break;
                case TabChar:
                    builder.Append('\t');
                    break;
                case Break:
                case CarriageReturn:
                    builder.Append('\n');
                    break;
            }
        }
        return builder.ToString();
    }

    public static int CodePointCount(string value) => value.EnumerateRunes().Count();

    public static string SliceCodePoints(string value, int start, int end)
    {
        var runes = value.EnumerateRunes().ToArray();
        if (start < 0 || end < start || end > runes.Length)
        {
            throw new ProcessorException("invalid_target", "The DOCX text range is out of bounds.");
        }
        return string.Concat(runes[start..end].Select(rune => rune.ToString()));
    }

    public static string ReplaceCodePoints(string value, int start, int end, string replacement) =>
        SliceCodePoints(value, 0, start) + replacement + SliceCodePoints(value, end, CodePointCount(value));

    public static void ReplaceRange(Paragraph paragraph, int start, int end, string replacement)
    {
        var leaves = VisibleLeaves(paragraph);
        var affected = leaves.Where(item => item.Start < end && item.End > start).ToArray();
        if (affected.Length == 0)
        {
            throw new ProcessorException("invalid_target", "The DOCX target has no text leaves.");
        }
        var hyperlinks = affected
            .SelectMany(item => item.Element.Ancestors<Hyperlink>())
            .Distinct()
            .ToArray();

        for (var index = 0; index < affected.Length; index++)
        {
            var item = affected[index];
            var localStart = Math.Max(start - item.Start, 0);
            var localEnd = Math.Min(end - item.Start, item.End - item.Start);
            var before = SliceCodePoints(item.Text, 0, localStart);
            var after = SliceCodePoints(item.Text, localEnd, item.End - item.Start);
            var value = before + (index == 0 ? replacement : string.Empty) + after;
            ReplaceLeaf(item.Element, value);
        }
        foreach (var hyperlink in hyperlinks)
        {
            foreach (var child in hyperlink.ChildElements.ToArray())
            {
                child.Remove();
                hyperlink.InsertBeforeSelf(child);
            }
            hyperlink.Remove();
        }
    }

    private sealed record VisibleLeaf(OpenXmlLeafElement Element, string Text, int Start, int End);

    private static IReadOnlyList<VisibleLeaf> VisibleLeaves(Paragraph paragraph)
    {
        var result = new List<VisibleLeaf>();
        var offset = 0;
        foreach (var leaf in paragraph.Descendants<OpenXmlLeafElement>())
        {
            if (leaf.Ancestors<Paragraph>().FirstOrDefault() != paragraph)
            {
                continue;
            }
            var value = leaf switch
            {
                Text text => text.Text,
                TabChar => "\t",
                Break => "\n",
                CarriageReturn => "\n",
                _ => null,
            };
            if (value is null)
            {
                continue;
            }
            var length = CodePointCount(value);
            result.Add(new VisibleLeaf(leaf, value, offset, offset + length));
            offset += length;
        }
        return result;
    }

    private static void ReplaceLeaf(OpenXmlLeafElement leaf, string value)
    {
        var buffer = new StringBuilder();
        void Flush()
        {
            if (buffer.Length == 0)
            {
                return;
            }
            leaf.InsertBeforeSelf(
                new Text(buffer.ToString()) { Space = SpaceProcessingModeValues.Preserve });
            buffer.Clear();
        }

        foreach (var character in value)
        {
            switch (character)
            {
                case '\t':
                    Flush();
                    leaf.InsertBeforeSelf(new TabChar());
                    break;
                case '\n':
                    Flush();
                    leaf.InsertBeforeSelf(new Break());
                    break;
                default:
                    buffer.Append(character);
                    break;
            }
        }
        Flush();
        leaf.Remove();
    }

    private static IEnumerable<Paragraph> Paragraphs(OpenXmlElement root)
    {
        foreach (var child in root.ChildElements)
        {
            if (child is Paragraph paragraph)
            {
                yield return paragraph;
            }
            foreach (var nested in Paragraphs(child))
            {
                yield return nested;
            }
        }
    }

    private static string BlockId(
        string sourceSha256,
        string storyKind,
        string partUri,
        string structuralPath)
    {
        var material = string.Join(
            '\0',
            sourceSha256,
            partUri,
            storyKind,
            structuralPath);
        var digest = SHA256.HashData(Encoding.UTF8.GetBytes(material));
        return "b_" + Convert.ToHexStringLower(digest);
    }
}
