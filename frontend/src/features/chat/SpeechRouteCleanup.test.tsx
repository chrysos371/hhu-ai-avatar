import { render, screen } from '@testing-library/react';
import { useLayoutEffect } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useSpeechPlayer } from './useSpeechPlayer';

let paused: boolean;
beforeEach(() => {
  paused=false;
  vi.spyOn(HTMLMediaElement.prototype,'paused','get').mockImplementation(()=>paused);
  vi.spyOn(HTMLMediaElement.prototype,'pause').mockImplementation(()=>{paused=true;});
  vi.spyOn(HTMLMediaElement.prototype,'load').mockImplementation(()=>{});
});
afterEach(()=>{vi.restoreAllMocks();});
function Chat(){const speech=useSpeechPlayer();return <audio data-testid="owned-audio" ref={speech.audioRef}/>;}

it('releases the detached audio before the destination layout observes its committed route',()=>{
  const observations:{paused:boolean;src:boolean}[]=[];
  const view=render(<Chat/>);const audio=screen.getByTestId('owned-audio') as HTMLAudioElement;
  audio.setAttribute('src','blob:owned-audio-fixture');
  function Destination(){
    useLayoutEffect(()=>{observations.push({paused:audio.paused,src:audio.hasAttribute('src')});},[]);
    return <h1>目标页</h1>;
  }
  view.rerender(<Destination/>);
  expect(observations).toEqual([{paused:true,src:false}]);
  expect(audio.isConnected).toBe(false);
});

it('keeps the owned audio during an ordinary rerender of the same chat',()=>{
  const view=render(<Chat/>);const audio=screen.getByTestId('owned-audio') as HTMLAudioElement;
  audio.setAttribute('src','blob:owned-audio-fixture');view.rerender(<Chat/>);
  expect(audio).toHaveAttribute('src','blob:owned-audio-fixture');expect(paused).toBe(false);
});
