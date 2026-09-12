import { useTracks, VideoTrack, type TrackReferenceOrPlaceholder } from "@livekit/components-react";
import { Track } from "livekit-client";

/** Every screen being shared in the room right now (yours included, as a local preview), oldest first. */
export function useScreenShares(): TrackReferenceOrPlaceholder[] {
  return useTracks([{ source: Track.Source.ScreenShare, withPlaceholder: false }], { onlySubscribed: false });
}

export function screenShareKey(t: TrackReferenceOrPlaceholder): string {
  return `${t.participant.identity}:${t.publication?.trackSid ?? "screen"}`;
}

export function screenShareLabel(t: TrackReferenceOrPlaceholder): string {
  return t.participant.isLocal ? "your screen" : `${t.participant.name || t.participant.identity}'s screen`;
}

/** One shared screen, letterboxed to fit the middle column. */
export function ScreenShareView({ track }: { track: TrackReferenceOrPlaceholder }) {
  return (
    <div className="screenshare">
      {track.publication ? (
        <VideoTrack trackRef={track} className="screenshare-video" />
      ) : (
        <p className="dim">connecting…</p>
      )}
      <p className="screenshare-cap dim">{screenShareLabel(track)}</p>
    </div>
  );
}
