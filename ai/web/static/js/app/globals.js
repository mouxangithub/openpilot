/**
 * Application-wide namespace for modular front-end pieces.
 * Legacy scripts attach capabilities here during migration.
 */
const App = {
  version: '2.0.0-arch',
  modules: {},
  register(name, api) {
    this.modules[name] = api;
  },
  get(name) {
    return this.modules[name];
  },
};

if (typeof ChatModelTag !== 'undefined') {
  App.register('ChatModelTag', ChatModelTag);
}
