using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Screens.MainMenu;

namespace RegentRL.RegentRLCode;

// NMainMenu.AbandonRun records abandoned run history and deletes the save
// directly; it does not call RunManager.OnEnded.
[HarmonyPatch(typeof(NMainMenu), nameof(NMainMenu.AbandonRun))]
public static class MainMenuAbandonLifecyclePatch
{
    // Postfix: only report an abandonment after the native method returned.
    // A fresh process may have no tracked run ID; don't forge one.
    [HarmonyPostfix]
    public static void Postfix()
    {
        RunLifecycleBridge.OnMainMenuAbandoned();
    }
}
