// Built-in audio plugins for the Studio: 3-band EQ, compressor, and de-esser,
// implemented with native WebAudio nodes. The microphone is routed through
// this chain and the processed output is what goes on the air.

export type AudioPluginSettings = {
  eq: { enabled: boolean; low: number; mid: number; high: number }; // gain in dB, -12..+12
  compressor: { enabled: boolean; threshold: number; ratio: number }; // dB, 1..20
  deEsser: { enabled: boolean; amount: number }; // dB of reduction around 6.5 kHz, 0..24
};

export const defaultAudioSettings: AudioPluginSettings = {
  eq: { enabled: false, low: 0, mid: 0, high: 0 },
  compressor: { enabled: false, threshold: -24, ratio: 4 },
  deEsser: { enabled: false, amount: 8 }
};

export type AudioChain = {
  context: AudioContext;
  lowShelf: BiquadFilterNode;
  midPeak: BiquadFilterNode;
  highShelf: BiquadFilterNode;
  deEsser: BiquadFilterNode;
  compressor: DynamicsCompressorNode;
  destination: MediaStreamAudioDestinationNode;
  input: MediaStreamAudioSourceNode | null;
};

export function createAudioChain(): AudioChain {
  const context = new AudioContext();

  const lowShelf = context.createBiquadFilter();
  lowShelf.type = "lowshelf";
  lowShelf.frequency.value = 200;

  const midPeak = context.createBiquadFilter();
  midPeak.type = "peaking";
  midPeak.frequency.value = 1000;
  midPeak.Q.value = 0.9;

  const highShelf = context.createBiquadFilter();
  highShelf.type = "highshelf";
  highShelf.frequency.value = 6000;

  // Sibilance sits around 5–8 kHz; a narrow negative peak tames it.
  const deEsser = context.createBiquadFilter();
  deEsser.type = "peaking";
  deEsser.frequency.value = 6500;
  deEsser.Q.value = 3.5;

  const compressor = context.createDynamicsCompressor();
  compressor.knee.value = 12;
  compressor.attack.value = 0.01;
  compressor.release.value = 0.2;

  const destination = context.createMediaStreamDestination();

  lowShelf.connect(midPeak);
  midPeak.connect(highShelf);
  highShelf.connect(deEsser);
  deEsser.connect(compressor);
  compressor.connect(destination);

  return { context, lowShelf, midPeak, highShelf, deEsser, compressor, destination, input: null };
}

/** Route a (new) microphone stream into the chain, replacing any previous one. */
export function connectAudioInput(chain: AudioChain, stream: MediaStream): void {
  chain.input?.disconnect();
  chain.input = chain.context.createMediaStreamSource(stream);
  chain.input.connect(chain.lowShelf);
}

/** Push settings into the live nodes; disabled plugins get neutral values. */
export function applyAudioSettings(chain: AudioChain, settings: AudioPluginSettings): void {
  const { eq, compressor, deEsser } = settings;
  chain.lowShelf.gain.value = eq.enabled ? eq.low : 0;
  chain.midPeak.gain.value = eq.enabled ? eq.mid : 0;
  chain.highShelf.gain.value = eq.enabled ? eq.high : 0;
  chain.deEsser.gain.value = deEsser.enabled ? -Math.abs(deEsser.amount) : 0;
  chain.compressor.threshold.value = compressor.enabled ? compressor.threshold : 0;
  chain.compressor.ratio.value = compressor.enabled ? compressor.ratio : 1;
}

export function closeAudioChain(chain: AudioChain): void {
  chain.input?.disconnect();
  void chain.context.close().catch(() => undefined);
}
