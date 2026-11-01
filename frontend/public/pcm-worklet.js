class PcmWorklet extends AudioWorkletProcessor {
  constructor(){super();this.pending=[];this.port.onmessage=e=>{if(e.data==='flush'){this.emit();this.port.postMessage({type:'flushed'});}}}
  emit(){if(!this.pending.length)return;const out=new Int16Array(this.pending.length);for(let i=0;i<out.length;i++){const n=Math.max(-1,Math.min(1,this.pending[i]));out[i]=n<0?n*32768:n*32767}this.port.postMessage({type:'audio',buffer:out.buffer},[out.buffer]);this.pending=[]}
  process(inputs){const input=inputs[0]?.[0];if(input){for(const value of input){this.pending.push(value);if(this.pending.length>=2048)this.emit()}}return true}
}
registerProcessor('pcm-worklet',PcmWorklet);
