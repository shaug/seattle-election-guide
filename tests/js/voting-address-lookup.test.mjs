import assert from 'node:assert/strict';
import test from 'node:test';
import { createVotingAddressLookup } from '../../src/election_guide/rendering/templates/voting-address-lookup.mjs';
import { assertModuleGuard } from './support/module-guards.mjs';

const context = {
  election_id: 'wa-2026-general',
  mapping_hash: 'reviewed',
  city: { item: 'city', data: 1, schema_edit: 2 },
  precinct: { item: 'precinct', data: 3, schema_edit: 4 },
  address: { item: 'address', data: 9, schema_edit: 5 },
};
const precincts = [
  {
    code: '0320',
    name: 'SEA 34-0320',
    jurisdiction_ids: [
      'congressional-district-7',
      'legislative-district-34',
      'county-council-district-8',
      'seattle-city-council-district-7',
    ],
  },
  {
    code: '0321',
    name: 'SEA 34-0321',
    jurisdiction_ids: [
      'congressional-district-7',
      'legislative-district-34',
      'county-council-district-8',
      'seattle-city-council-district-1',
    ],
  },
];
const suggestion = {
  text: '600 4TH AVE, Seattle, WA, 98104',
  magicKey: 'selected',
  isCollection: false,
};
const meta = (key) => ({
  serviceItemId: context[key].item,
  editingInfo: {
    dataLastEditDate: context[key].data ?? 9,
    schemaLastEditDate: context[key].schema_edit,
  },
});
const sites = {
  spatialReference: { wkid: 4326 },
  features: [
    {
      attributes: {
        SITEID: 'public-civic',
        ADDR_FULL: '600 4TH AVE',
        ZIP5: '98104',
        Unit: null,
        Building: null,
      },
      geometry: { x: -122.33, y: 47.6 },
    },
  ],
};
const district = {
  VOTDST: '0320',
  NAME: 'SEA 34-0320',
  CONGDST: '7',
  LEGDST: '34',
  KCCDST: '8',
  SCC: '7',
};
function transport(change = {}) {
  const calls = [];
  const fetchImpl = async (url, options) => {
    calls.push({ url, options });
    const form = new URLSearchParams(options.body);
    let value;
    if (url.endsWith('/suggest')) value = { suggestions: [suggestion] };
    else if (url.endsWith('/findAddressCandidates'))
      value = {
        candidates: [
          {
            address: suggestion.text,
            score: 100,
            attributes: {
              Addr_type: 'PointAddress',
              StAddr: '600 4TH AVE',
              Postal: '98104',
              SubAddr: '',
            },
            location: { x: -1, y: -1 },
          },
        ],
      };
    else if (!url.endsWith('/query'))
      value = meta(
        url.includes('CITY_AREA') ? 'city' : url.includes('March2026') ? 'precinct' : 'address',
      );
    else if (url.includes('ADDRESS_POINT')) value = structuredClone(sites);
    else if (url.includes('CITY_AREA'))
      value = { features: [{ attributes: { CITYNAME: 'Seattle', JURIS: 'SE' } }] };
    else value = { features: [{ attributes: { ...district } }] };
    value = change.edit?.(value, url, form) ?? value;
    if (change.error) throw new Error('private raw provider URL/address');
    return new Response(JSON.stringify(value), { status: change.status ?? 200 });
  };
  return { fetchImpl, calls };
}
const boot = (change = {}, binding = context) => {
  const t = transport(change);
  return {
    ...t,
    lookup: createVotingAddressLookup(binding, precincts, { fetchImpl: t.fetchImpl }),
  };
};
test('explicit canonical selection uses current exact sites and returns leading-zero catalog identity only', async () => {
  const b = boot();
  assert.deepEqual(await b.lookup.suggest('600 4th', new AbortController().signal), [suggestion]);
  assert.deepEqual(await b.lookup.resolve(suggestion, new AbortController().signal), {
    status: 'resolved',
    code: '0320',
  });
  const pointCalls = b.calls.filter(
    (c) => c.url.endsWith('/query') && !c.url.includes('ADDRESS_POINT'),
  );
  assert.ok(
    pointCalls.every(
      (c) => JSON.parse(new URLSearchParams(c.options.body).get('geometry')).x === -122.33,
    ),
  );
  for (const c of b.calls) {
    assert.equal(c.options.credentials, 'omit');
    assert.equal(c.options.cache, 'no-store');
    assert.equal(c.options.referrerPolicy, 'no-referrer');
    assert.equal(c.options.method, c.url.endsWith('?f=json') ? 'GET' : 'POST');
    assert.ok(!c.url.includes('600'));
  }
});
for (const kind of [
  'postal-city',
  'unknown-code',
  'tuple',
  'name',
  'boundary',
  'truncated',
  'bad-SR',
  'NaN',
  'unit',
  'approximate',
  'missing-site',
  'drift',
]) {
  test(`resolution fails closed: ${kind}`, async () => {
    const b = boot({
      edit: (v, url) => {
        if (kind === 'drift' && !url.endsWith('/query') && url.includes('March2026'))
          v.editingInfo.dataLastEditDate++;
        if (url.endsWith('/findAddressCandidates')) {
          if (kind === 'unit') v.candidates[0].attributes.SubAddr = 'APT 2';
          if (kind === 'approximate') v.candidates[0].attributes.Addr_type = 'StreetAddress';
        }
        if (url.endsWith('/query')) {
          if (kind === 'truncated') v.exceededTransferLimit = true;
          if (url.includes('ADDRESS_POINT')) {
            if (kind === 'bad-SR') v.spatialReference.wkid = 2926;
            if (kind === 'NaN') v.features[0].geometry.x = null;
            if (kind === 'missing-site') v.features = [];
          }
          if (url.includes('CITY_AREA') && kind === 'postal-city') v.features = [];
          if (url.includes('March2026')) {
            if (kind === 'unknown-code') v.features[0].attributes.VOTDST = '9999';
            if (kind === 'tuple') v.features[0].attributes.LEGDST = '46';
            if (kind === 'name') v.features[0].attributes.NAME = 'wrong';
            if (kind === 'boundary')
              v.features.push({ attributes: { ...district, VOTDST: '1111' } });
          }
        }
        return v;
      },
    });
    assert.notEqual(
      (await b.lookup.resolve(suggestion, new AbortController().signal)).status,
      'resolved',
    );
  });
}
test('no capability, wrong election, partial text and collections issue no lookup requests', async () => {
  for (const binding of [null, { ...context, election_id: 'wa-2026-primary' }]) {
    const b = boot({}, binding);
    assert.deepEqual(await b.lookup.suggest('600', new AbortController().signal), []);
    assert.notEqual(
      (await b.lookup.resolve(suggestion, new AbortController().signal)).status,
      'resolved',
    );
    assert.equal(b.calls.length, 0);
  }
  const b = boot();
  assert.deepEqual(await b.lookup.suggest('x', new AbortController().signal), []);
  assert.notEqual(
    (await b.lookup.resolve({ ...suggestion, isCollection: true }, new AbortController().signal))
      .status,
    'resolved',
  );
  assert.equal(b.calls.length, 0);
});
for (const status of [429, 500])
  test(`bounded transport failure ${status} exposes no provider text`, async () => {
    const b = boot({ status });
    assert.deepEqual(await b.lookup.resolve(suggestion, new AbortController().signal), {
      status: 'unavailable',
    });
  });
test('exceptions and HTTP200 GIS error payload fail without leaking details', async () => {
  for (const options of [
    { error: true },
    { edit: () => ({ error: { message: 'private address' } }) },
  ]) {
    assert.deepEqual(await boot(options).lookup.resolve(suggestion, new AbortController().signal), {
      status: 'unavailable',
    });
  }
});
test('lookup has no storage capability', () => assertModuleGuard('voting-address-lookup.mjs'));

test('a selected exact subaddress resolves only when complete exact unit site scope agrees', async () => {
  const unitSuggestion = { ...suggestion, text: '600 4TH AVE APT 2, Seattle, WA, 98104' };
  const b = boot({
    edit: (v, url, form) => {
      if (url.endsWith('/findAddressCandidates')) {
        v.candidates[0].address = unitSuggestion.text;
        Object.assign(v.candidates[0].attributes, {
          UnitName: '2',
          UnitType: 'APT',
          SubAddr: 'APT 2',
        });
      }
      if (url.endsWith('/query') && url.includes('ADDRESS_POINT')) {
        assert.match(form.get('where'), /AND Unit = '2'$/);
        v.features[0].attributes.Unit = '2';
      }
      return v;
    },
  });
  assert.deepEqual(await b.lookup.resolve(unitSuggestion, new AbortController().signal), {
    status: 'resolved',
    code: '0320',
  });
});

test('missing address-point edit metadata cannot masquerade as an unchanged snapshot', async () => {
  const b = boot({
    edit: (v, url) => {
      if (url.includes('ADDRESS_POINT') && !url.endsWith('/query'))
        delete v.editingInfo.dataLastEditDate;
      return v;
    },
  });
  assert.notEqual(
    (await b.lookup.resolve(suggestion, new AbortController().signal)).status,
    'resolved',
  );
});

for (const kind of [
  'same-address-conflict',
  'same-code-conflict',
  'missing-fields',
  'metadata-after',
  'point-version-after',
])
  test(`complete scope validation rejects ${kind}`, async () => {
    let cityReads = 0;
    let addressReads = 0;
    const b = boot({
      edit: (v, url) => {
        if (!url.endsWith('/query') && url.includes('CITY_AREA')) {
          cityReads++;
          if (kind === 'metadata-after' && cityReads > 1) v.editingInfo.dataLastEditDate++;
        }
        if (!url.endsWith('/query') && url.includes('ADDRESS_POINT')) {
          addressReads++;
          if (kind === 'point-version-after' && addressReads > 1) v.editingInfo.dataLastEditDate++;
        }
        if (
          url.endsWith('/query') &&
          url.includes('ADDRESS_POINT') &&
          kind === 'same-address-conflict'
        )
          v.features.push({ ...structuredClone(v.features[0]), geometry: { x: -123, y: 47 } });
        if (
          url.endsWith('/query') &&
          url.includes('CITY_AREA') &&
          kind === 'same-address-conflict'
        ) {
          if (
            b.calls.filter((c) => c.url.includes('CITY_AREA') && c.url.endsWith('/query')).length >
            1
          )
            v.features = [];
        }
        if (url.endsWith('/query') && url.includes('March2026')) {
          if (kind === 'same-code-conflict')
            v.features.push({ attributes: { ...district, SCC: '1' } });
          if (kind === 'missing-fields') delete v.features[0].attributes.LEGDST;
        }
        return v;
      },
    });
    assert.notEqual(
      (await b.lookup.resolve(suggestion, new AbortController().signal)).status,
      'resolved',
    );
  });

test('exact-address SQL literals cannot add clauses and response labels remain data', async () => {
  const address = "O'NEIL %_ AVE";
  const b = boot({
    edit: (v, url, form) => {
      if (url.endsWith('/findAddressCandidates')) v.candidates[0].attributes.StAddr = address;
      if (url.endsWith('/query') && url.includes('ADDRESS_POINT')) {
        assert.equal(form.get('where'), "ADDR_FULL = 'O''NEIL %_ AVE' AND ZIP5 = '98104'");
        v.features[0].attributes.ADDR_FULL = address;
      }
      return v;
    },
  });
  assert.equal(
    (await b.lookup.resolve(suggestion, new AbortController().signal)).status,
    'resolved',
  );
});

test('oversized or non-JSON responses are bounded and never retried', async () => {
  for (const body of ['x'.repeat(262145), '<html>not a GIS response</html>']) {
    let count = 0;
    const lookup = createVotingAddressLookup(context, precincts, {
      fetchImpl: async () => {
        count++;
        return new Response(body);
      },
    });
    assert.deepEqual(await lookup.resolve(suggestion, new AbortController().signal), {
      status: 'unavailable',
    });
    assert.equal(count, 1);
  }
});

test('fixed address-free metadata uses the documented GET shape; address-bearing operations use POST', async () => {
  const b = boot();
  await b.lookup.resolve(suggestion, new AbortController().signal);
  const metadata = b.calls.filter(
    (c) => !c.url.includes('/query') && !c.url.includes('/findAddressCandidates'),
  );
  assert.equal(metadata.length, 6);
  assert.ok(
    metadata.every(
      (c) =>
        c.options.method === 'GET' && c.url.endsWith('?f=json') && c.options.body === undefined,
    ),
  );
});

test('a missing reviewed source context disables suggestions before any address transmission', async () => {
  const b = boot({}, { ...context, city: null });
  assert.deepEqual(await b.lookup.suggest('600 4th', new AbortController().signal), []);
  assert.equal(b.calls.length, 0);
});

test('a stalled native-style request aborts at the bounded deadline without retries', async () => {
  let calls = 0;
  let aborted = false;
  const lookup = createVotingAddressLookup(context, precincts, {
    fetchImpl: async (_url, options) => {
      calls += 1;
      return new Promise((_resolve, reject) => {
        options.signal.addEventListener(
          'abort',
          () => {
            aborted = true;
            reject(new DOMException('Aborted', 'AbortError'));
          },
          { once: true },
        );
      });
    },
  });
  assert.deepEqual(await lookup.suggest('600 4th', new AbortController().signal), []);
  assert.equal(aborted, true);
  assert.equal(calls, 1);
});

test('numeric and spaced prefixes are transmitted verbatim without a street-word classifier', async () => {
  const b = boot();
  for (const text of ['2857', '2857 n']) {
    assert.deepEqual(await b.lookup.suggest(text, new AbortController().signal), [suggestion]);
  }
  assert.deepEqual(
    b.calls.map((call) => new URLSearchParams(call.options.body).get('text')),
    ['2857', '2857 n'],
  );
});

// Synthetic catalog-supported geography, not a claim about the public civic site's ballot.
const secondDistrict = {
  VOTDST: '0321',
  NAME: 'SEA 34-0321',
  CONGDST: '7',
  LEGDST: '34',
  KCCDST: '8',
  SCC: '1',
};

test('two individually supported precincts in one intersection fail closed', async () => {
  const resolve = async (districts) => {
    const b = boot({
      edit: (value, url) => {
        if (url.endsWith('/query') && url.includes('March2026'))
          value.features = districts.map((attributes) => ({ attributes }));
        return value;
      },
    });
    return b.lookup.resolve(suggestion, new AbortController().signal);
  };
  assert.deepEqual(await resolve([district]), { status: 'resolved', code: '0320' });
  assert.deepEqual(await resolve([secondDistrict]), { status: 'resolved', code: '0321' });
  for (const districts of [
    [district, secondDistrict],
    [secondDistrict, district],
  ])
    assert.deepEqual(await resolve(districts), { status: 'unresolved' });
});

test('two individually supported precincts across exact Seattle sites fail closed', async () => {
  const firstSite = structuredClone(sites.features[0]);
  const secondSite = structuredClone(firstSite);
  secondSite.attributes.SITEID = 'public-civic-second';
  secondSite.geometry.x = -122.331;
  const resolve = async (selectedSites) => {
    const b = boot({
      edit: (value, url, form) => {
        if (url.endsWith('/query') && url.includes('ADDRESS_POINT')) value.features = selectedSites;
        if (url.endsWith('/query') && url.includes('March2026')) {
          const point = JSON.parse(form.get('geometry'));
          value.features = [
            {
              attributes: point.x === firstSite.geometry.x ? district : secondDistrict,
            },
          ];
        }
        return value;
      },
    });
    return b.lookup.resolve(suggestion, new AbortController().signal);
  };
  assert.deepEqual(await resolve([firstSite]), { status: 'resolved', code: '0320' });
  assert.deepEqual(await resolve([secondSite]), { status: 'resolved', code: '0321' });
  for (const selectedSites of [
    [firstSite, secondSite],
    [secondSite, firstSite],
  ])
    assert.deepEqual(await resolve(selectedSites), { status: 'unresolved' });
});
