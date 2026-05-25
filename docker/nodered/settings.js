// Node-RED settings — entorno Docker SISCOM
module.exports = {
    // El archivo de flujos a cargar
    flowFile: 'flows.json',

    // Deshabilita encriptación de credenciales → flows_cred.json en plaintext
    // (el token InfluxDB se inyecta por variable de entorno en el entrypoint)
    credentialSecret: false,

    userDir: '/data/',
    nodesDir: '/data/nodes/',

    uiPort: process.env.PORT || 1880,
    uiHost: '0.0.0.0',

    logging: {
        console: {
            level: 'info',
            metric: false,
            audit: false
        }
    },

    // Permite acceso sin autenticación (entorno académico/demo)
    adminAuth: null,

    // Contexto global para compartir variables entre nodos
    functionGlobalContext: {
        influx_token: process.env.INFLUX_TOKEN || ''
    }
}
