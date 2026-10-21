using System.IO;
using System.Text.Json;
using System.Collections.Generic;

namespace RegentRL.RegentRLCode;

public static class CombatExperienceBuffer
{
    private static readonly List<CombatTransition> _transitions = new();

    public static int Count => _transitions.Count;

    public static void Add(CombatTransition transition)
    {
        _transitions.Add(transition);
    }

    public static void Clear()
    {
        _transitions.Clear();
    }

    public static IReadOnlyList<CombatTransition> GetAll()
    {
        return _transitions.AsReadOnly();
    }

    public static void SaveToFile(string path)
    {
        var options = new JsonSerializerOptions
        {
            WriteIndented = true
        };

        string json = JsonSerializer.Serialize(_transitions, options);

        File.WriteAllText(path, json);
    }
}
