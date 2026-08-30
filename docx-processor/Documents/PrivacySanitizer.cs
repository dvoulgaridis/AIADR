using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx.Documents;

internal static class PrivacySanitizer
{
    public static SanitationSummary Sanitize(WordprocessingDocument document)
    {
        var main = document.MainDocumentPart
            ?? throw new ProcessorException("invalid_docx", "The DOCX has no main document part.");
        var documentRoot = main.Document
            ?? throw new ProcessorException("invalid_docx", "The DOCX has no main document part.");
        var commentCount = main.WordprocessingCommentsPart?.Comments?.Elements<Comment>().Count() ?? 0;

        var roots = StoryRoots(main).ToArray();
        foreach (var root in roots)
        {
            NormalizeAlternateContent(root);
            foreach (var marker in root.Descendants<CommentRangeStart>().ToArray())
            {
                marker.Remove();
            }
            foreach (var marker in root.Descendants<CommentRangeEnd>().ToArray())
            {
                marker.Remove();
            }
            foreach (var marker in root.Descendants<CommentReference>().ToArray())
            {
                marker.Remove();
            }
        }
        if (main.WordprocessingCommentsPart is not null)
        {
            main.DeletePart(main.WordprocessingCommentsPart);
        }

        var propertiesRemoved = 0;
        var properties = document.PackageProperties;
        propertiesRemoved += Clear(() => properties.Creator, value => properties.Creator = value);
        propertiesRemoved += Clear(() => properties.LastModifiedBy, value => properties.LastModifiedBy = value);
        propertiesRemoved += Clear(() => properties.Title, value => properties.Title = value);
        propertiesRemoved += Clear(() => properties.Subject, value => properties.Subject = value);
        propertiesRemoved += Clear(() => properties.Keywords, value => properties.Keywords = value);
        propertiesRemoved += Clear(() => properties.Description, value => properties.Description = value);
        propertiesRemoved += Clear(() => properties.Category, value => properties.Category = value);
        propertiesRemoved += Clear(() => properties.ContentStatus, value => properties.ContentStatus = value);

        if (document.ExtendedFilePropertiesPart is not null)
        {
            document.DeletePart(document.ExtendedFilePropertiesPart);
            propertiesRemoved += 1;
        }
        if (document.CustomFilePropertiesPart is not null)
        {
            document.DeletePart(document.CustomFilePropertiesPart);
            propertiesRemoved += 1;
        }

        foreach (var root in roots)
        {
            root.Save();
        }
        return new SanitationSummary(commentCount, propertiesRemoved);
    }

    private static IEnumerable<OpenXmlPartRootElement> StoryRoots(MainDocumentPart main)
    {
        if (main.Document is not null)
        {
            yield return main.Document;
        }
        foreach (var header in main.HeaderParts.OrderBy(part => part.Uri.ToString()))
        {
            if (header.Header is not null)
            {
                yield return header.Header;
            }
        }
        foreach (var footer in main.FooterParts.OrderBy(part => part.Uri.ToString()))
        {
            if (footer.Footer is not null)
            {
                yield return footer.Footer;
            }
        }
        if (main.FootnotesPart?.Footnotes is not null)
        {
            yield return main.FootnotesPart.Footnotes;
        }
        if (main.EndnotesPart?.Endnotes is not null)
        {
            yield return main.EndnotesPart.Endnotes;
        }
    }

    private static void NormalizeAlternateContent(OpenXmlElement root)
    {
        foreach (var alternate in root.Descendants<AlternateContent>().Reverse().ToArray())
        {
            OpenXmlCompositeElement? selected = alternate.Elements<AlternateContentChoice>().FirstOrDefault();
            selected ??= alternate.GetFirstChild<AlternateContentFallback>();
            if (selected is not null)
            {
                foreach (var child in selected.ChildElements)
                {
                    alternate.InsertBeforeSelf(child.CloneNode(true));
                }
            }
            alternate.Remove();
        }
    }

    private static int Clear(Func<string?> get, Action<string?> set)
    {
        if (string.IsNullOrEmpty(get()))
        {
            return 0;
        }
        set(null);
        return 1;
    }
}
