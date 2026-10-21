using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Threading;

namespace RegentRL.RegentRLCode;

public static class PythonAgentClient
{
    public static async Task<CombatDecisionResponse?> RequestActionAsync(
        CombatDecisionRequest request)
    {
        using var client = new TcpClient();
        using var timeout = new CancellationTokenSource(
                TimeSpan.FromSeconds(5)
                );

        await client.ConnectAsync("127.0.0.1", 5050, timeout.Token);

        using NetworkStream stream = client.GetStream();
        using var writer = new StreamWriter(
            stream,
            new UTF8Encoding(false),
            leaveOpen: true
        );

        using var reader = new StreamReader(
            stream,
            Encoding.UTF8
        );

        string requestJson = JsonSerializer.Serialize(request);

        await writer.WriteLineAsync(requestJson);
        await writer.FlushAsync();

        string? responseJson = await reader.ReadLineAsync(timeout.Token);

        if (responseJson == null)
        {
            throw new IOException("Python closed the connection without responding.");
        }

        return JsonSerializer.Deserialize<CombatDecisionResponse>(responseJson);
    }
}
