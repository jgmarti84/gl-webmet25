/**
 * Base path (spec base-path): the prefix the site is served under, '' at the root or '/nacho' behind a proxy that
 * strips it. nginx writes it into <base href> of every page, so relative URLs (fetch, links, redirects) already
 * stay inside it. These helpers are only for code that compares or builds full browser paths.
 */

/** Prefix of this page, read from <base href> ('' at the root). Without a document (node tests) it is ''. */
export function basePath(baseURI = typeof document === 'undefined' ? null : document.baseURI) {
    if (!baseURI) return '';
    return new URL(baseURI).pathname.replace(/\/+$/, '');
}

/** A browser path without the prefix: appPath('/nacho/login', '/nacho') === '/login'. */
export function appPath(pathname, base = basePath()) {
    if (!base) return pathname;
    if (pathname === base) return '/';
    return pathname.startsWith(`${base}/`) ? pathname.slice(base.length) : pathname;
}
