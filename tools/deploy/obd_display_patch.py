
# BOUNDED_DISPLAY_PATCH
def display(plugin_context, cursor, config_encrypted, display_encrypt_password='******', *args, **kwargs):
    stdio = plugin_context.stdio
    stdio.start_loading('Wait for seekdb init')
    cluster_config = plugin_context.cluster_config
    if not config_encrypted:
        display_encrypt_password = None
    if plugin_context.get_variable('restart_manager'):
        cursor = plugin_context.get_return('connect').get_return('cursor')
    deadline = time.time() + 180
    last_error = 'oceanbase.__all_server returned no rows'
    while time.time() < deadline:
        try:
            servers = cursor.fetchall('select * from oceanbase.__all_server', raise_exception=True, exc_level='verbose')
        except Exception as exc:
            code = exc.args[0] if exc.args else None
            last_error = 'oceanbase.__all_server query failed: %r' % (exc,)
            if code not in (1146, 4012):
                raise
            time.sleep(3)
            continue
        if not servers:
            last_error = 'oceanbase.__all_server is empty'
            time.sleep(3)
            continue
        stdio.print_list(servers, ['ip', 'version', 'port', 'zone', 'status'],
            lambda x: [x['svr_ip'], x['build_version'].split('_')[0], x['inner_port'], x['zone'], x['status']], title=cluster_config.name)
        user = 'root'
        password = cluster_config.get_global_conf().get('root_password', '') if not display_encrypt_password else display_encrypt_password
        cmd = 'obclient -h%s -P%s -uroot %s-Doceanbase -A' % (servers[0]['svr_ip'], servers[0]['inner_port'], '-p%s ' % passwd_format(password) if password else '')
        stdio.print(cmd)
        stdio.stop_loading('succeed')
        info_dict = {
            "type": "db",
            "ip": servers[0]['svr_ip'],
            "port": servers[0]['inner_port'],
            "user": user,
            "password": password,
            "cmd": cmd
        }
        unique_id = None
        try:
            var = cursor.fetchone('select unix_timestamp(gmt_create) as gmt_create from oceanbase.__all_virtual_sys_variable limit 1', raise_exception=True, exc_level='verbose')
        except Exception:
            var = None
        if var:
            cid = int(var['gmt_create'] * 1000)
            unique_id = Codec.encoding(cid, servers[0]['build_version'])
            stdio.print('cluster unique id: %s\\n' % unique_id)
        plugin_context.set_variable('server_infos', servers)
        return plugin_context.return_true(info=info_dict, unique_id=unique_id)
    stdio.stop_loading('fail', 'seekdb display did not converge: %s' % last_error)
    stdio.print('display diagnostics: %s' % last_error)
    server = cluster_config.servers[0]
    server_config = cluster_config.get_server_conf(server)
    password = cluster_config.get_global_conf().get('root_password', '') if not display_encrypt_password else display_encrypt_password
    info_dict = {
        "type": "db",
        "ip": server.ip,
        "port": server_config.get('mysql_port', 2881),
        "user": 'root',
        "password": password,
    }
    plugin_context.set_variable('server_infos', [])
    return plugin_context.return_true(info=info_dict)
