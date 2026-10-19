// What the Live tab says before the first candidate has been handed out. A run spends a minute or two in this state while
// the GPUs load the model, so it must not read as "nothing happened"; only a run that has ended without any work says that.

const ENDED = new Set(['COMPLETED', 'CANCELLED', 'FAILED']);

export function emptyLiveText(status: string): { title: string; message: string } {
  return ENDED.has(status)
    ? { title: 'Nothing has run yet', message: 'This experiment ended before any candidate ran.' }
    : {
        title: 'Starting up',
        message:
          'The GPUs are loading the model, which can take a minute or two. This view fills in as soon as the coordinator hands out the first candidate.',
      };
}
