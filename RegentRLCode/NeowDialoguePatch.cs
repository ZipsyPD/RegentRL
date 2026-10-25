using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;

namespace RegentRL.RegentRLCode;

[HarmonyPatch(
    typeof(NAncientEventLayout),
    "UpdateFakeNextButton"
)]
public static class NeowDialoguePatch
{
    [HarmonyPostfix]
    public static void Postfix(NAncientEventLayout __instance)
    {
        if (!GodotObject.IsInstanceValid(__instance))
            return;

        var hitbox = __instance.GetNodeOrNull<NButton>(
            "%DialogueHitbox"
        );

        if (hitbox == null ||
            !hitbox.Visible ||
            !hitbox.IsEnabled)
            return;

        __instance.CallDeferred("OnDialogueHitboxClicked", hitbox);
    }
}
