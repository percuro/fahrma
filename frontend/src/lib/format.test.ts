import { describe, expect, it } from 'vitest';
import { createFormat, parseKm, parseMoney, parseQuantity } from './format';

describe('parseMoney', () => {
  it('accepts German and English notation', () => {
    expect(parseMoney('12,50')).toBe(1250);
    expect(parseMoney('12.50')).toBe(1250);
    expect(parseMoney('12.5')).toBe(1250);
    expect(parseMoney('12')).toBe(1200);
    expect(parseMoney(' 7,05 € ')).toBe(705);
    expect(parseMoney('1.234,56')).toBe(123456);
    expect(parseMoney('1,234.56')).toBe(123456);
    expect(parseMoney('1 234,56')).toBe(123456);
  });

  it('reads three digits after a single separator as thousands', () => {
    expect(parseMoney('1.234')).toBe(123400);
    expect(parseMoney('1,234')).toBe(123400);
    expect(parseMoney('1.234.567')).toBe(123456700);
  });

  it('rejects empty and invalid input', () => {
    expect(parseMoney('')).toBeNull();
    expect(parseMoney('abc')).toBeNull();
    expect(parseMoney('-5')).toBeNull();
    expect(parseMoney('1,2345')).toBeNull();
  });
});

describe('parseQuantity and parseKm', () => {
  it('parses litres or kWh with up to three decimals', () => {
    expect(parseQuantity('42,5')).toBe(42500);
    expect(parseQuantity('42.5')).toBe(42500);
    expect(parseQuantity('40')).toBe(40000);
    expect(parseQuantity('1,234')).toBe(1234);
    expect(parseQuantity('0')).toBeNull();
    expect(parseQuantity('1,2345')).toBeNull();
  });

  it('ignores thousands separators in km', () => {
    expect(parseKm('12.345')).toBe(12345);
    expect(parseKm('12,345')).toBe(12345);
    expect(parseKm('12 345')).toBe(12345);
    expect(parseKm('12345 km')).toBe(12345);
    expect(parseKm('')).toBeNull();
    expect(parseKm('12a')).toBeNull();
  });
});

describe('createFormat', () => {
  const de = createFormat('de', 'EUR');
  const en = createFormat('en', 'GBP');

  it('formats km and dates per language', () => {
    expect(de.km(12345)).toBe('12.345 km');
    expect(en.km(12345)).toBe('12,345 km');
    expect(de.km(null)).toBe('–');
    expect(de.date('2026-11-24')).toBe('24.11.2026');
    expect(de.date('2026-11-24T10:00:00')).toBe('24.11.2026');
    expect(en.date('2026-11-24')).toBe('24/11/2026');
  });

  it('uses the group currency', () => {
    expect(de.money(1250)).toMatch(/12,50\s€/);
    expect(en.money(1250)).toBe('£12.50');
    expect(en.signedMoney(1250)).toBe('+£12.50');
    expect(en.signedMoney(-300)).toBe('-£3.00');
    expect(en.rate(30)).toBe('£0.300/km');
    expect(en.currencySymbol).toBe('£');
  });

  it('formats quantities, unit prices and input values', () => {
    expect(de.quantity(42500, 'l')).toBe('42,5 l');
    expect(en.quantity(42500, 'kWh')).toBe('42.5 kWh');
    expect(en.unitPrice(1500, 30000, 'kWh')).toBe('£0.500/kWh');
    expect(de.moneyInput(1250)).toBe('12,50');
    expect(en.moneyInput(1250)).toBe('12.50');
    expect(parseMoney(de.moneyInput(99_999))).toBe(99_999);
    expect(de.quantityInput(42500)).toBe('42,5');
    expect(de.moneyInput(null)).toBe('');
  });
});
