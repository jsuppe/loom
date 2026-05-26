// Reference solution for s_aggregate.
//
// Public contract:
//   aggregate(events, opts) -> object
//
//   events: array of event objects
//   opts: { groupBy: string, reducers: { [outKey]: { initial: any, step: (acc, event) => any } } }
//
//   Returns an object keyed by the distinct values of event[opts.groupBy].
//   Each group's value is an object whose keys are opts.reducers's keys and
//   whose values are the result of folding the group's events through
//   reducers[k].step starting from reducers[k].initial.
//
// Style (M22e s_aggregate rationale): inputs are treated as immutable.
// Neither the events array nor any event object is mutated. New objects
// are produced for accumulators via the reducer pass.

export function aggregate(events, opts) {
  if (!Array.isArray(events)) {
    throw new TypeError('events must be an array');
  }
  if (!opts || typeof opts.groupBy !== 'string' || !opts.reducers || typeof opts.reducers !== 'object') {
    throw new TypeError('opts must include groupBy (string) and reducers (object)');
  }

  const groupKey = opts.groupBy;
  const reducerEntries = Object.entries(opts.reducers);
  const groups = {};

  for (const event of events) {
    const key = event[groupKey];
    if (!Object.prototype.hasOwnProperty.call(groups, key)) {
      const seed = {};
      for (const [outKey, spec] of reducerEntries) {
        seed[outKey] = spec.initial;
      }
      groups[key] = seed;
    }
    const prior = groups[key];
    const next = {};
    for (const [outKey, spec] of reducerEntries) {
      next[outKey] = spec.step(prior[outKey], event);
    }
    groups[key] = next;
  }

  return groups;
}
