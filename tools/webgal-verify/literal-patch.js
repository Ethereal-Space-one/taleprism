/* Storygal literal text extension for WebGAL 4.6.5, MPL-2.0.
 * Source fragment inserted at the beginning of compileSentence (Na in the pinned build).
 * Six hex digits per Unicode code point keep source text outside WebGAL's executable syntax.
 * Returning plain React text nodes bypasses interpolation, ruby, style and escape processing.
 * The supplied engine bundle is modified only by the insertion of this fragment.
 */
if (/^SGTEXT_(?:[0-9a-f]{6})+$/.test(e)) {
  return [e.slice(7).match(/.{6}/g).map(function (hex) {
    return {reactNode: String.fromCodePoint(parseInt(hex, 16))};
  })];
}
