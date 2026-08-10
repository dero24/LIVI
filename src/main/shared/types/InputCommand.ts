export enum InputCommand {
  Play = 'play',
  Pause = 'pause',
  PlayPause = 'playPause',
  Stop = 'stop',
  Next = 'next',
  Previous = 'previous',
  FastForward = 'fastForward',
  Rewind = 'rewind',
  VolumeUp = 'volumeUp',
  VolumeDown = 'volumeDown',
  Mute = 'mute',
  AcceptCall = 'acceptCall',
  RejectCall = 'rejectCall',
  HookSwitch = 'hookSwitch',
  VoiceAssistant = 'voiceAssistant',
  // [hub] AA navigation: Home goes to the AA dashboard/app grid,
  // Back returns to the previous screen. Used by the landing page
  // to navigate to specific apps via sendCommand('home') + touch replay.
  Home = 'home',
  Back = 'back'
}

export type InputCommandKey = `${InputCommand}`

export function isInputCommand(value: unknown): value is InputCommand {
  return typeof value === 'string' && (Object.values(InputCommand) as string[]).includes(value)
}
