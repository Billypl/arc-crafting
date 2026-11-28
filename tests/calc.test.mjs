// Testy kalkulatora (calcRun w index.html): pełne crafty, zapas, „nie craftuj”, wspólne półprodukty, alternatywy.
//   node --test tests/
// Skrypt strony jest uruchamiany w vm z namiastką DOM; strona oddaje swoje funkcje przez globalThis.__arcTest.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const main = scripts.find(s => s.includes("__arcTest"));
assert.ok(main, "w index.html nie ma skryptu z haczykiem __arcTest");

// Element, który przyjmuje każde wywołanie i przypisanie (strona przy starcie podpina zdarzenia i pisze w DOM).
const stub = () => {
  const fn = function () {};
  return new Proxy(fn, {
    get: (t, k) => k === Symbol.toPrimitive ? () => "" : k === "then" ? undefined : k === "length" ? 0 : el,
    set: () => true,
    apply: () => el,
    construct: () => el,
  });
};
const el = stub();

// Świeża kopia strony z podanymi danymi; zwraca jej funkcje kalkulatora.
function load(data, calc = {}) {
  let api;
  const ctx = {
    document: el, window: el, navigator: el, location: { hash: "" }, history: el,
    localStorage: { getItem: () => null, setItem() {} },
    fetch: () => new Promise(() => {}),
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    requestAnimationFrame: () => 0, ResizeObserver: class { observe() {} }, getComputedStyle: () => el,
    setTimeout, clearTimeout, console, Intl,
    __arcTest: a => { api = a; },
  };
  ctx.globalThis = ctx;
  vm.runInNewContext(main, ctx);
  assert.ok(api, "haczyk __arcTest nie został wywołany");
  api.index({ items: {}, recipes: [], recycle: [], upgrades: [], projects: [], quests: [], ...data });
  Object.assign(api.CALC, { list: [], keep: [], have: {} }, calc);
  // Obiekty z vm mają własne prototypy (Array z innego realm); klon daje zwykłe tablice do deepStrictEqual.
  return { ...api, calcRun: () => structuredClone(api.calcRun()) };
}

const r = (out, ins, qty = 1, stations = ["Workbench 1"]) => ({ out, qty, in: ins, stations, blueprint: null, skill: null });
const byN = rows => Object.fromEntries(rows.map(x => [x.n, x]));

test("niepełny craft zaokrągla w górę i mnoży składniki", () => {
  const { calcRun } = load({ recipes: [r("Ammo", [["Metal", 2]], 3)] }, { list: [["Ammo", 4]] });
  const { crafts, raw } = calcRun();
  assert.equal(crafts.length, 1);
  assert.deepEqual([crafts[0].k, crafts[0].made, crafts[0].need], [2, 6, 4]);
  assert.deepEqual(raw.map(x => [x.n, x.need]), [["Metal", 4]]);
});

test("wspólny półprodukt liczony łącznie, zanim zaokrąglimy", () => {
  // Dwa cele potrzebują po 1 Gear; jeden craft daje 2 Gear, więc wystarczy jeden, nie dwa.
  const { calcRun } = load({
    recipes: [r("A", [["Gear", 1]]), r("B", [["Gear", 1]]), r("Gear", [["Metal", 5]], 2)],
  }, { list: [["A", 1], ["B", 1]] });
  const c = byN(calcRun().crafts);
  assert.equal(c.Gear.k, 1);
  assert.equal(c.Gear.lvl, 1);
  assert.deepEqual(calcRun().raw.map(x => [x.n, x.need]), [["Metal", 5]]);
});

test("zapas odejmuje się od zapotrzebowania na każdym poziomie", () => {
  const recipes = [r("Gun", [["Part", 2], ["Metal", 1]]), r("Part", [["Metal", 3]])];
  // 1 Part w zapasie: craftujemy 1 Part (3 Metal) + 1 Metal na broń, z czego 2 Metal mamy.
  const { calcRun } = load({ recipes }, { list: [["Gun", 1]], have: { Part: 1, Metal: 2 } });
  const { crafts, raw } = calcRun();
  const c = byN(crafts);
  assert.deepEqual([c.Part.need, c.Part.own, c.Part.k], [2, 1, 1]);
  assert.deepEqual(raw.map(x => [x.n, x.need, x.own, x.rest]), [["Metal", 4, 2, 2]]);
});

test("zapas pokrywający półprodukt w całości: zero craftów i brak jego składników", () => {
  const { calcRun } = load({ recipes: [r("Gun", [["Part", 2]]), r("Part", [["Metal", 3]])] },
    { list: [["Gun", 1]], have: { Part: 5 } });
  const c = byN(calcRun().crafts);
  assert.equal(c.Part.k, 0);
  assert.deepEqual(calcRun().raw, []);
});

test("„nie craftuj” zamienia półprodukt w surowiec", () => {
  const { calcRun } = load({ recipes: [r("Gun", [["Part", 2]]), r("Part", [["Metal", 3]])] },
    { list: [["Gun", 1]], keep: ["Part"] });
  const { crafts, raw } = calcRun();
  assert.deepEqual(crafts.map(x => x.n), ["Gun"]);
  assert.deepEqual(raw.map(x => [x.n, x.need]), [["Part", 2]]);
});

test("cele idą na koniec listy craftów, najgłębsze półprodukty na początek", () => {
  const { calcRun } = load({ recipes: [r("Gun", [["Part", 1]]), r("Part", [["Bolt", 1]]), r("Bolt", [["Metal", 1]])] },
    { list: [["Gun", 1]] });
  assert.deepEqual(calcRun().crafts.map(x => [x.n, x.lvl]), [["Bolt", 2], ["Part", 1], ["Gun", 0]]);
});

test("alternatywy: surowiec, który w całości idzie przez półprodukt", () => {
  // Cały Metal idzie przez Part, a Part przez Bolt: „albo 1× Bolt, albo 2× Part”, najbliższy surowcowi pierwszy.
  const { calcRun } = load({ recipes: [r("Gun", [["Part", 2]]), r("Part", [["Bolt", 1]]), r("Bolt", [["Metal", 3]])] },
    { list: [["Gun", 1]] });
  const raw = byN(calcRun().raw);
  assert.deepEqual(raw.Metal.alts.map(a => a.c.n), ["Bolt", "Part"]);
  // Cel nie jest alternatywą (jego i tak trzeba zrobić).
  assert.ok(!raw.Metal.alts.some(a => a.c.n === "Gun"));
});

test("alternatywy: brak, gdy surowiec idzie dwiema drogami", () => {
  const { calcRun } = load({ recipes: [r("Gun", [["Part", 1], ["Metal", 1]]), r("Part", [["Metal", 3]])] },
    { list: [["Gun", 1]] });
  assert.deepEqual(byN(calcRun().raw).Metal.alts, []);
});

test("alternatywy przy częściowym zapasie półproduktu liczą resztę", () => {
  // 2 Bolt potrzebne, 1 w zapasie: craft 1 Bolt (3 Metal); Metal dalej w całości idzie przez Bolt i Part.
  const { calcRun } = load({ recipes: [r("Gun", [["Part", 2]]), r("Part", [["Bolt", 1]]), r("Bolt", [["Metal", 3]])] },
    { list: [["Gun", 1]], have: { Bolt: 1 } });
  const { crafts, raw } = calcRun();
  assert.deepEqual([byN(crafts).Bolt.own, byN(crafts).Bolt.k], [1, 1]);
  assert.equal(byN(raw).Metal.need, 3);
  assert.deepEqual(byN(raw).Metal.alts.map(a => a.c.n), ["Bolt", "Part"]);
});

test("przepis w rajdzie wybierany przełącznikiem", () => {
  const recipes = [
    r("Bandage", [["Cloth", 2]], 1, ["Medical Lab 1"]),
    r("Bandage", [["Fabric", 14]], 1, ["Inventory"]),
    r("Cloth", [["Fabric", 5]]),
  ];
  const a = load({ recipes }, { list: [["Bandage", 1]] });
  assert.deepEqual(a.calcRun().raw.map(x => [x.n, x.need]), [["Fabric", 10]]);
  a.opt.raid = true;
  assert.deepEqual(a.calcRun().raw.map(x => [x.n, x.need]), [["Fabric", 14]]);
});

test("na prawdziwym data.json: każdy przepis daje spójny wynik", () => {
  const data = JSON.parse(readFileSync(new URL("../data.json", import.meta.url), "utf8"));
  const outs = [...new Set(data.recipes.map(x => x.out))];
  const api = load(data);
  for (const n of outs) {
    Object.assign(api.CALC, { list: [[n, 3]], keep: [], have: {} });
    const { crafts, raw } = api.calcRun();
    for (const c of crafts) {
      assert.ok(c.made >= c.rest, `${n}: ${c.n} zrobione ${c.made} < potrzebne ${c.rest}`);
      assert.equal(c.made, c.k * c.r.qty);
    }
    for (const x of raw) assert.ok(x.need > 0 && x.rest === x.need, `${n}: ${x.n}`);
    assert.equal(crafts.at(-1).n, n);
  }
});
