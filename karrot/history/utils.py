def without_keys(d, keys):
    """
    Return a new dict with a list of keys stripped from it

    :param d: input dict
    :param keys: list of keys to strip
    :return: new dict
    """
    return {x: d[x] for x in d if x not in keys}
