
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;

using MegaCrit.Sts2.Core.Entities.CardRewardAlternatives;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.TestSupport;

namespace RegentRL.RegentRLCode;

public class RegentRLCardSelector : ICardSelector
{
    private static readonly List<CardSelectionExperience> _pendingSelections = new();

    public static List<CardSelectionExperience> TakePendingSelections()
    {
        var result = _pendingSelections.ToList();
        _pendingSelections.Clear();
        return result;
    }

    public async Task<IEnumerable<CardModel>> GetSelectedCards(
        IEnumerable<CardModel> options,
        int minSelect,
        int maxSelect)
    {
        var cards = options.ToList();

        MainFile.Logger.Info(
                $"REGENTRL SELECTOR: Python requested for {cards.Count} cards, " +
                $"min={minSelect}, max={maxSelect}"
                );

        var context = CardSelectionPurposePatch.Current;

        var request = new CardSelectionRequest
        {
            DecisionId = CardSelectionDecisionIds.Next(),
            RunObservation = cards.Count > 0 ? RunObservationExtractor.Extract(cards[0].Owner) : null,
            Purpose = context.Purpose,
            Source = context.Source,
            MinSelect = minSelect,
            MaxSelect = maxSelect,
            Options = cards.Select(card => card.Id.Entry).ToList(),
            OptionDetails = cards.Select((card, index) => new CardSelectionOption
            {
                Index = index,
                CardId = card.Id.Entry,
                UpgradeLevel = card.CurrentUpgradeLevel
            }).ToList()
        };

        MainFile.Logger.Info(
            $"REGENTRL SELECTOR PURPOSE: " +
            $"Purpose={request.Purpose}, Source={request.Source}"
        );

        CardSelectionResponse? response;

        try
        {
            response = await PythonAgentClient.RequestCardSelectionAsync(request);
        }
        catch (Exception ex)
        {
            MainFile.Logger.Info(
                    $"REGENTRL SELECTOR ERROR: {ex.Message}"
                    );
            throw;
        }

        if (response == null || response.DecisionId != request.DecisionId)
            throw new InvalidOperationException("Invalid Python card-selection response.");

        var indices = response.SelectedIndices;

        if (indices == null ||
                indices.Count < minSelect ||
                indices.Count > Math.Min(maxSelect, cards.Count) ||
                indices.Distinct().Count() != indices.Count ||
                indices.Any(i => i < 0 || i >= cards.Count))
        {
            throw new InvalidOperationException("Python returned an illegal card selection.");
        }

        var selected = indices.Select(i => cards[i]).ToList();

        _pendingSelections.Add(new CardSelectionExperience
        {
            DecisionId = request.DecisionId,
            Purpose = request.Purpose,
            Source = request.Source,
            Options = request.Options.ToList(),
            MinSelect = request.MinSelect,
            MaxSelect = request.MaxSelect,
            SelectedIndices = indices.ToList()
        });

        MainFile.Logger.Info(
                $"REGENTRL SELECTOR: Python selected {selected.Count} card(s)"
                );

        return selected;
    }

    public CardRewardSelection GetSelectedCardReward(
        IReadOnlyList<CardCreationResult> options,
        IReadOnlyList<CardRewardAlternative> alternatives)
    {
        // Temporary deterministic behavior for testing.
        // We will implement Python-controlled rewards separately.
        if (options.Count == 0)
            return default;

        return new CardRewardSelection
        {
            card = options[0].Card,
            alternative = null
        };
    }
}

internal static class CardSelectionDecisionIds
{
    private static long _nextId;

    public static long Next()
    {
        return System.Threading.Interlocked.Increment(ref _nextId);
    }
}

