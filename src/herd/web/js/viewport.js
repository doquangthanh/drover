// One definition of "phone layout", identical to the CSS media queries in css/mobile*.css:
// a narrow window, or a touch device turned sideways (short viewport).
export const PHONE_MQ = "(max-width: 760px), (pointer: coarse) and (max-height: 500px)";

const mq = matchMedia(PHONE_MQ);

export const isPhone = () => mq.matches;

/** Run fn when the window switches between the phone and the desktop/tablet layout (rotate, resize, fold). */
export function onLayoutChange(fn) {
  mq.addEventListener("change", fn);
}
