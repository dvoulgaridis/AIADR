using System.IO.Compression;
using Aiadr.Docx.Protocol;

namespace Aiadr.Docx.Documents;

internal static class PackageArchivePolicy
{
    private const int MaxEntryCount = 2_048;
    private const long MaxEntryBytes = 50L * 1024 * 1024;
    private const long MaxExpandedBytes = 200L * 1024 * 1024;
    private const int MaxCompressionRatio = 200;

    public static void Validate(string path)
    {
        using var archive = ZipFile.OpenRead(path);
        if (archive.Entries.Count > MaxEntryCount)
        {
            throw Unsupported("entry_count", "The DOCX contains too many package entries.");
        }

        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long expandedBytes = 0;
        foreach (var entry in archive.Entries)
        {
            ValidateName(entry.FullName);
            if (!names.Add(entry.FullName))
            {
                throw Unsupported("duplicate_entry", "The DOCX contains duplicate package entries.");
            }
            if (entry.Length > MaxEntryBytes)
            {
                throw Unsupported("entry_size", "A DOCX package entry is too large.");
            }
            expandedBytes = checked(expandedBytes + entry.Length);
            if (expandedBytes > MaxExpandedBytes)
            {
                throw Unsupported("expanded_size", "The expanded DOCX package is too large.");
            }
            if (entry.CompressedLength > 0
                && entry.Length > entry.CompressedLength * MaxCompressionRatio)
            {
                throw Unsupported("compression_ratio", "A DOCX package entry is compressed excessively.");
            }
        }
    }

    private static void ValidateName(string name)
    {
        var partName = name.TrimEnd('/');
        if (string.IsNullOrWhiteSpace(partName)
            || partName.Contains("\\", StringComparison.Ordinal)
            || partName.StartsWith("/", StringComparison.Ordinal)
            || partName.Split('/').Any(segment => segment is "" or "." or ".."))
        {
            throw Unsupported("entry_name", "The DOCX contains an unsafe package entry name.");
        }
    }

    private static ProcessorException Unsupported(string feature, string message) =>
        new("unsupported_docx_feature", message, feature);
}
