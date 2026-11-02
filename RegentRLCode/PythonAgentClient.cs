using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using System.Threading;

namespace RegentRL.RegentRLCode;

public static class PythonAgentClient
{
    // Adds the same logical run ID to every existing request type without
    // changing any of the working native decision handlers.
    private static string SerializeRequest(object request)
    {
        JsonNode node = JsonSerializer.SerializeToNode(request)
            ?? throw new InvalidOperationException("Empty decision request");
        if (node is not JsonObject obj)
            throw new InvalidOperationException("Decision request must be an object");
        obj["RunId"] = RunLifecycleBridge.EnsureRunId();
        return obj.ToJsonString();
    }

    public static async Task<CombatDecisionResponse?> RequestActionAsync(
        CombatDecisionRequest request)
    {
        using var client = new TcpClient();
        using var timeout = new CancellationTokenSource(
                TimeSpan.FromMinutes(3)
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

        string requestJson = SerializeRequest(request);

        await writer.WriteLineAsync(requestJson);
        await writer.FlushAsync();

        string? responseJson = await reader.ReadLineAsync(timeout.Token);

        if (responseJson == null)
        {
            throw new IOException("Python closed the connection without responding.");
        }

        return JsonSerializer.Deserialize<CombatDecisionResponse>(responseJson);
    }

    public static async Task<CardSelectionResponse?> RequestCardSelectionAsync(
            CardSelectionRequest request)
    {
        using var client = new TcpClient();
        using var timeout = new CancellationTokenSource(
                TimeSpan.FromMinutes(3)
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

        string requestJson = SerializeRequest(request);

        await writer.WriteLineAsync(requestJson);
        await writer.FlushAsync();

        string? responseJson = await reader.ReadLineAsync(timeout.Token);

        if (responseJson == null)
        {
            throw new IOException(
                    "Python closed the card-selection connection without respond."
                    );
        }


        return JsonSerializer.Deserialize<CardSelectionResponse>(responseJson);
    }
    
    public static async Task<RewardDecisionResponse?>
        RequestRewardDecisionAsync(RewardDecisionRequest request)
    {
        using var client = new TcpClient();

        await client.ConnectAsync("127.0.0.1", 5050);

        using NetworkStream stream = client.GetStream();
        using var writer = new StreamWriter(stream, new UTF8Encoding(false))
        {
            AutoFlush = true
        };
        using var reader = new StreamReader(stream);

        string json = SerializeRequest(request);
        await writer.WriteLineAsync(json);

        string? responseJson = await reader.ReadLineAsync();

        if (string.IsNullOrWhiteSpace(responseJson))
            throw new InvalidOperationException(
                "Python returned an empty reward decision response.");

        return JsonSerializer.Deserialize<RewardDecisionResponse>(
            responseJson
        );
    }
 
    public static async Task<CombatDecisionResponse?> RequestNeowDecisionAsync(
        object request)
    {
        using var client = new TcpClient();
        using var timeout = new CancellationTokenSource(
            TimeSpan.FromMinutes(3)
        );

        await client.ConnectAsync("127.0.0.1", 5050, timeout.Token);

        using NetworkStream stream = client.GetStream();
        using var writer = new StreamWriter(
            stream, new UTF8Encoding(false), leaveOpen: true
        );
        using var reader = new StreamReader(stream, Encoding.UTF8);

        await writer.WriteLineAsync(SerializeRequest(request));
        await writer.FlushAsync();

        string? responseJson = await reader.ReadLineAsync(timeout.Token);

        if (string.IsNullOrWhiteSpace(responseJson))
            throw new IOException("Empty Python Neow response");

        return JsonSerializer.Deserialize<CombatDecisionResponse>(responseJson);
    }

}
