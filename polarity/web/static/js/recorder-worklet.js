// AudioWorklet processor: forwards mono Float32 chunks from the microphone to the main thread.
class PolarityRecorder extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0] && input[0].length) {
      this.port.postMessage(input[0].slice(0));
    }
    return true;
  }
}

registerProcessor("polarity-recorder", PolarityRecorder);
