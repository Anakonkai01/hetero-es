// Plain-language definitions of the words a newcomer meets (English text is the translation key).
export const GLOSSARY: Record<string, string> = {
  candidate: "One randomly nudged copy of the model. It is tested on a GPU and gets a score.",
  seed: "A number that recreates exactly the same random nudge on any computer, so nothing but the number has to be sent.",
  reward: "The score a candidate earns on the task. Higher is better; it is not an accuracy or a percentage.",
  generation: "One round: nudge the model many ways, test every nudge, then update the model once.",
  checkpoint: "A saved copy of the model's weights after a generation, so a run can be recovered or reused.",
  lease: "Permission for one GPU to evaluate one candidate within a deadline. If it is not finished in time, another GPU may take it.",
  replay: "Rebuilding the new model from the recorded updates instead of downloading all its weights again.",
  coordinator: "The computer that hands out candidates, collects scores and updates the model.",
  worker: "A GPU computer that evaluates candidates for the lab.",
};
