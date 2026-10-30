/** Covered scope membership is independent of sources and current race visibility.
 * @param {ReadonlyArray<{value:string,contest_ids?:string[]}>} scopes
 * @param {Set<string>|null} eligible
 */
export function availableBallotScopes(scopes, eligible) {
  return new Set(
    scopes
      .filter(
        (scope) =>
          scope.value === 'all' ||
          eligible === null ||
          scope.contest_ids?.some((id) => eligible.has(id)),
      )
      .map((scope) => scope.value),
  );
}

/** Preserve the renderer's option/group nodes; values identify projection targets only.
 * @param {HTMLSelectElement} select
 */
export function makeBallotScopeProjector(select) {
  const groups = [...select.children].map((element) => ({
    element,
    options: /** @type {HTMLOptionElement[]} */ (
      element.tagName === 'OPTGROUP' ? [...element.children] : [element]
    ),
  }));
  /** @param {Set<string>} available */
  return (available) => {
    const value = select.value;
    const shown = [];
    for (const group of groups) {
      const options = group.options.filter((option) => available.has(option.value));
      if (group.element.tagName === 'OPTGROUP') group.element.replaceChildren(...options);
      if (options.length) shown.push(group.element);
    }
    select.replaceChildren(...shown);
    select.value = available.has(value) ? value : 'all';
  };
}
