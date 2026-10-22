/** Match the backend's contiguous-token source policy and retain original offsets. */
export function sourceSpans(text: string, quote: string): Array<[number, number]> {
  const tokenize = (value: string) => [...value.matchAll(/[\p{L}\p{N}_]+[+#]*/gu)];
  const actual = tokenize(text);
  const wanted = tokenize(quote).map(m => m[0].normalize("NFKC").toLowerCase());
  const spans: Array<[number, number]> = [];
  if (!wanted.length) return spans;
  for (let i = 0; i <= actual.length - wanted.length; i++) {
    if (wanted.every((word, j) => actual[i + j][0].normalize("NFKC").toLowerCase() === word)) {
      const last = actual[i + wanted.length - 1];
      spans.push([actual[i].index!, last.index! + last[0].length]);
      i += wanted.length - 1;
    }
  }
  return spans;
}
