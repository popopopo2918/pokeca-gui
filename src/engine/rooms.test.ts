import { describe, expect, it } from 'vitest';
import { __test } from './rooms';

describe('room playback metadata', () => {
  it('marks every remotely polled frame animate', () => {
    expect(__test.remotePlayback(3)).toEqual(['animate', 'animate', 'animate']);
  });

  it('preserves sender playback metadata', () => {
    expect(__test.senderPlayback(['instant', 'animate'], 2)).toEqual(['instant', 'animate']);
    expect(__test.senderPlayback(undefined, 2)).toEqual(['animate', 'animate']);
  });
});
