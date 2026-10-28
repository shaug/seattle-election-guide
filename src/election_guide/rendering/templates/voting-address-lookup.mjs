// Optional, anonymous County/Esri lookup. No address leaves this adapter except as
// transient suggestions; the control commits only an admitted precinct code.
const LOCATOR =
  'https://gismaps.kingcounty.gov/arcgis/rest/services/Address/Address_Points_locator/GeocodeServer';
const GIS = 'https://services.arcgis.com/Ej0PsM5Aw677QF1W/arcgis/rest/services/';
const ADDRESS = `${GIS}ADDRESS_POINT_642/FeatureServer/0`;
const CITY = `${GIS}CITY_AREA_448/FeatureServer/0`;
const PRECINCT = `${GIS}FindMyDistricts_March2026/FeatureServer/655`;
const LIMIT = 20;
const MAX_BYTES = 262144;
const unresolved = () => ({ status: 'unresolved' });
const unavailable = () => ({ status: 'unavailable' });

/** @param {AddressLookupContext|null|undefined} binding @param {PrecinctContests[]} precincts
 * @param {{fetchImpl?: typeof fetch}} [options] */
export function createVotingAddressLookup(binding, precincts, { fetchImpl = fetch } = {}) {
  const enabled =
    binding?.election_id === 'wa-2026-general' &&
    typeof binding.mapping_hash === 'string' &&
    Boolean(binding.mapping_hash) &&
    ['city', 'precinct', 'address'].every((key) => {
      const source = binding?.[/** @type {"city"|"precinct"|"address"} */ (key)];
      return (
        typeof source?.item === 'string' &&
        Boolean(source.item) &&
        Number.isSafeInteger(source.data) &&
        source.data >= 0 &&
        Number.isSafeInteger(source.schema_edit) &&
        source.schema_edit >= 0
      );
    });
  /** @param {string} url @param {Record<string,string>} form @param {AbortSignal} signal */
  async function request(url, form, signal) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) controller.abort();
    const timer = setTimeout(abort, 10000);
    try {
      const metadata = Object.keys(form).length === 0;
      const response = await fetchImpl(metadata ? `${url}?f=json` : url, {
        method: metadata ? 'GET' : 'POST',
        ...(metadata ? {} : { body: new URLSearchParams({ f: 'json', ...form }) }),
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok || !response.body || controller.signal.aborted)
        throw new Error('lookup unavailable');
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let bytes = 0;
      let text = '';
      try {
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          bytes += chunk.value.byteLength;
          if (bytes > MAX_BYTES || controller.signal.aborted) throw new Error('lookup unavailable');
          text += decoder.decode(chunk.value, { stream: true });
        }
        text += decoder.decode();
      } finally {
        await reader.cancel();
      }
      const value = JSON.parse(text);
      if (!value || value.error || controller.signal.aborted || signal.aborted)
        throw new Error('lookup unavailable');
      return value;
    } finally {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
    }
  }
  /** @param {any} value */
  function features(value) {
    if (
      value.exceededTransferLimit ||
      !Array.isArray(value.features) ||
      value.features.length === 0 ||
      value.features.length >= LIMIT
    )
      throw new Error('incomplete lookup');
    return value.features;
  }
  /** @param {AbortSignal} signal */
  async function context(signal) {
    for (const [key, url] of /** @type {const} */ ([
      ['city', CITY],
      ['precinct', PRECINCT],
      ['address', ADDRESS],
    ])) {
      const data = await request(url, {}, signal);
      const expected = binding?.[key];
      if (
        !expected ||
        data.serviceItemId !== expected.item ||
        data.editingInfo?.schemaLastEditDate !== expected.schema_edit ||
        (key !== 'address' && data.editingInfo?.dataLastEditDate !== expected.data)
      )
        throw new Error('unreviewed geography');
      if (
        !Number.isSafeInteger(data.editingInfo?.dataLastEditDate) ||
        !Number.isSafeInteger(data.editingInfo?.schemaLastEditDate)
      )
        throw new Error('missing source identity');
      if (key === 'address') return data.editingInfo.dataLastEditDate;
    }
  }
  /** @param {string} text @param {AbortSignal} signal */
  async function suggest(text, signal) {
    if (!enabled || text.trim().length < 3 || text.length > 300) return [];
    try {
      const data = await request(`${LOCATOR}/suggest`, { text, maxSuggestions: '5' }, signal);
      if (!Array.isArray(data.suggestions) || data.suggestions.length > 5) return [];
      return data.suggestions.filter(
        (/** @type {any} */ s) =>
          typeof s.text === 'string' &&
          s.text.length <= 300 &&
          typeof s.magicKey === 'string' &&
          s.magicKey.length <= 4096 &&
          s.isCollection === false,
      );
    } catch {
      return [];
    }
  }
  /** @param {any} suggestion @param {AbortSignal} signal
   * @returns {Promise<{status:string,code?:string}>} */
  async function resolve(suggestion, signal) {
    if (
      !enabled ||
      !suggestion ||
      suggestion.isCollection !== false ||
      typeof suggestion.text !== 'string' ||
      suggestion.text.length > 300 ||
      typeof suggestion.magicKey !== 'string' ||
      suggestion.magicKey.length > 4096
    )
      return unresolved();
    try {
      const addressVersion = await context(signal);
      const data = await request(
        `${LOCATOR}/findAddressCandidates`,
        {
          SingleLine: suggestion.text,
          magicKey: suggestion.magicKey,
          outFields: '*',
          outSR: '4326',
          maxLocations: '2',
        },
        signal,
      );
      if (!Array.isArray(data.candidates) || data.candidates.length !== 1) return unresolved();
      const candidate = data.candidates[0];
      const a = candidate.attributes;
      if (
        candidate.address !== suggestion.text ||
        a?.Addr_type !== 'PointAddress' ||
        typeof a.StAddr !== 'string' ||
        !a.StAddr ||
        a.StAddr.length > 120 ||
        !/^\d{5}$/.test(a.Postal)
      )
        return unresolved();
      const unit = a.UnitName || '';
      const mentionsUnit = /(?:\b(?:APT|UNIT|SUITE|STE|FLOOR)\b|#)/i.test(suggestion.text);
      if (
        unit
          ? typeof unit !== 'string' ||
            !/^[A-Za-z0-9 -]{1,30}$/.test(unit) ||
            typeof a.SubAddr !== 'string' ||
            !a.SubAddr ||
            !suggestion.text.toUpperCase().includes(a.SubAddr.toUpperCase())
          : a.SubAddr || a.UnitType || mentionsUnit
      )
        return unresolved();
      const literal = a.StAddr.replaceAll("'", "''");
      const current = await request(
        `${ADDRESS}/query`,
        {
          where: `ADDR_FULL = '${literal}' AND ZIP5 = '${a.Postal}'${unit ? ` AND Unit = '${unit}'` : ''}`,
          outFields: 'OBJECTID,SITEID,ADDR_FULL,CTYNAME,POSTALCTYNAME,ZIP5,Building,Unit',
          outSR: '4326',
          returnGeometry: 'true',
          resultRecordCount: String(LIMIT),
        },
        signal,
      );
      if (current.spatialReference?.wkid !== 4326) return unresolved();
      let code = /** @type {string|null} */ (null);
      for (const site of features(current)) {
        const point = site.geometry;
        if (
          site.attributes?.ADDR_FULL !== a.StAddr ||
          site.attributes.ZIP5 !== a.Postal ||
          !site.attributes.SITEID ||
          (unit ? site.attributes.Unit !== unit : Boolean(site.attributes.Unit)) ||
          site.attributes.Building ||
          typeof point?.x !== 'number' ||
          typeof point.y !== 'number' ||
          !Number.isFinite(point.x) ||
          !Number.isFinite(point.y) ||
          Math.abs(point.x) > 180 ||
          Math.abs(point.y) > 90
        )
          return unresolved();
        const form = {
          where: '1=1',
          geometry: JSON.stringify(point),
          geometryType: 'esriGeometryPoint',
          inSR: '4326',
          spatialRel: 'esriSpatialRelIntersects',
          returnGeometry: 'false',
          resultRecordCount: String(LIMIT),
        };
        const cities = features(
          await request(`${CITY}/query`, { ...form, outFields: 'CITYNAME,JURIS' }, signal),
        );
        if (
          !cities.every(
            (/** @type {any} */ f) =>
              f.attributes?.CITYNAME === 'Seattle' && f.attributes.JURIS === 'SE',
          )
        )
          return unresolved();
        const districts = features(
          await request(
            `${PRECINCT}/query`,
            { ...form, outFields: 'VOTDST,NAME,CONGDST,LEGDST,KCCDST,SCC' },
            signal,
          ),
        );
        for (const f of districts) {
          const d = f.attributes;
          const match = precincts.find((p) => p.code === d?.VOTDST && p.name === d.NAME);
          if (!match?.jurisdiction_ids || (code !== null && code !== d.VOTDST)) return unresolved();
          for (const [field, prefix] of [
            ['CONGDST', 'congressional-district-'],
            ['LEGDST', 'legislative-district-'],
            ['KCCDST', 'county-council-district-'],
            ['SCC', 'seattle-city-council-district-'],
          ]) {
            if (
              typeof d[field] !== 'string' ||
              !/^\d+$/.test(d[field]) ||
              !match.jurisdiction_ids.includes(`${prefix}${d[field]}`)
            )
              return unresolved();
          }
          code = d.VOTDST;
        }
      }
      if ((await context(signal)) !== addressVersion || signal.aborted || code === null)
        return unresolved();
      return { status: 'resolved', code };
    } catch {
      return unavailable();
    }
  }
  return { suggest, resolve };
}
