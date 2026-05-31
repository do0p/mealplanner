import { formatQty } from './settings.service';

describe('formatQty', () => {
  describe('null quantity', () => {
    it('returns empty string with no unit', () => expect(formatQty(null, null)).toBe(''));
    it('returns unit string', () => expect(formatQty(null, 'g')).toBe('g'));
    it('returns empty string for pcs unit', () => expect(formatQty(null, 'pcs')).toBe(''));
  });

  describe('pcs unit — ceiling, no label', () => {
    it('keeps whole number', () => expect(formatQty(2, 'pcs')).toBe('2'));
    it('rounds up fractional value', () => expect(formatQty(1.1, 'pcs')).toBe('2'));
    it('rounds up at half', () => expect(formatQty(2.5, 'pcs')).toBe('3'));
    it('omits the pcs label', () => expect(formatQty(3, 'pcs')).toBe('3'));
  });

  describe('g / ml — round to nearest 5 above 10', () => {
    it('rounds down to 10', () => expect(formatQty(12, 'g')).toBe('10 g'));
    it('rounds up to 15', () => expect(formatQty(13, 'g')).toBe('15 g'));
    it('keeps exact multiples of 5', () => expect(formatQty(100, 'ml')).toBe('100 ml'));
    it('rounds to 1 decimal below 10', () => expect(formatQty(3.14, 'g')).toBe('3.1 g'));
    it('keeps whole numbers below 10', () => expect(formatQty(5, 'g')).toBe('5 g'));
  });

  describe('culinary units — fraction notation', () => {
    it('renders 1/2', () => expect(formatQty(0.5, 'cup')).toBe('1/2 cup'));
    it('renders 1/4', () => expect(formatQty(0.25, 'cup')).toBe('1/4 cup'));
    it('renders 3/4', () => expect(formatQty(0.75, 'tbsp')).toBe('3/4 tbsp'));
    it('renders whole + fraction', () => expect(formatQty(1.5, 'cup')).toBe('1 1/2 cup'));
    it('renders whole number when no fraction matches', () => expect(formatQty(2, 'cup')).toBe('2 cup'));
  });
});
