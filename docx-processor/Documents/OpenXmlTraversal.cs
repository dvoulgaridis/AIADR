using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx.Documents;

internal sealed record DocumentStory(
    string Kind,
    string PartUri,
    OpenXmlPart Part,
    OpenXmlElement Root);

internal static class OpenXmlTraversal
{
    public static IEnumerable<DocumentStory> Stories(WordprocessingDocument document)
    {
        var main = document.MainDocumentPart
            ?? throw new ProcessorException("invalid_docx", "The DOCX has no main document part.");
        var body = main.Document?.Body
            ?? throw new ProcessorException("invalid_docx", "The DOCX has no document body.");
        yield return new DocumentStory("body", main.Uri.ToString(), main, body);

        foreach (var part in main.HeaderParts.OrderBy(part => part.Uri.ToString()))
        {
            if (part.Header is not null)
            {
                yield return new DocumentStory("header", part.Uri.ToString(), part, part.Header);
            }
        }
        foreach (var part in main.FooterParts.OrderBy(part => part.Uri.ToString()))
        {
            if (part.Footer is not null)
            {
                yield return new DocumentStory("footer", part.Uri.ToString(), part, part.Footer);
            }
        }
        if (main.FootnotesPart?.Footnotes is not null)
        {
            yield return new DocumentStory(
                "footnote",
                main.FootnotesPart.Uri.ToString(),
                main.FootnotesPart,
                main.FootnotesPart.Footnotes);
        }
        if (main.EndnotesPart?.Endnotes is not null)
        {
            yield return new DocumentStory(
                "endnote",
                main.EndnotesPart.Uri.ToString(),
                main.EndnotesPart,
                main.EndnotesPart.Endnotes);
        }
    }

    public static string StructuralPath(OpenXmlElement element, OpenXmlElement root)
    {
        var segments = new Stack<string>();
        OpenXmlElement? current = element;
        while (current is not null && current != root)
        {
            var index = current.Parent?.Elements().TakeWhile(item => item != current)
                .Count(item => item.LocalName == current.LocalName) ?? 0;
            segments.Push($"{current.LocalName}[{index}]");
            current = current.Parent;
        }
        if (current is null)
        {
            throw new ProcessorException("invalid_docx", "An Open XML element has no story root.");
        }
        return root.LocalName + "/" + string.Join('/', segments);
    }
}
