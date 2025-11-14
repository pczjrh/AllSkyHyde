@app.route('/api/sftp/transfer', methods=['POST'])
def sftp_transfer_images():
    """Transfer all images to FTP or sFTP server"""
    global app_settings

    try:
        # Check if FTP/sFTP is configured
        if not all([app_settings.get('ftp_server'),
                   app_settings.get('ftp_username'),
                   app_settings.get('ftp_password'),
                   app_settings.get('ftp_remote_path')]):
            return jsonify({
                "status": "error",
                "message": "FTP/sFTP not configured. Please fill in all FTP settings."
            }), 400

        protocol = app_settings.get('ftp_protocol', 'ftp').lower()

        print("="*80)
        print(f"{protocol.upper()} TRANSFER REQUESTED")
        print("="*80)
        app.logger.info(f"{protocol.upper()} transfer started")

        ftp_server = app_settings['ftp_server']
        ftp_port = app_settings.get('ftp_port', 21 if protocol == 'ftp' else 22)
        ftp_username = app_settings['ftp_username']
        ftp_password = app_settings['ftp_password']
        ftp_remote_path = app_settings['ftp_remote_path']

        print(f"Connecting to {ftp_username}@{ftp_server}:{ftp_port}")
        app.logger.info(f"Connecting to {ftp_username}@{ftp_server}:{ftp_port}")

        # Get all images
        image_pattern = os.path.join(IMAGE_DIR, "*_exp*ms.png")
        image_files = glob.glob(image_pattern)

        if not image_files:
            return jsonify({
                "status": "error",
                "message": "No images found to transfer"
            }), 404

        print(f"Found {len(image_files)} images to transfer")
        app.logger.info(f"Found {len(image_files)} images to transfer")

        # Validate connection parameters
        print(f"Protocol: {protocol.upper()}")
        print(f"Server: {ftp_server}")
        print(f"Port: {ftp_port}")
        print(f"Username: {ftp_username}")
        print(f"Remote path: {ftp_remote_path}")

        transferred = 0
        skipped = 0
        errors = 0

        if protocol == 'sftp':
            # sFTP transfer using paramiko
            import paramiko

            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            try:
                # Connect to SSH server
                print(f"Attempting sFTP connection...")
                ssh.connect(
                    hostname=ftp_server,
                    port=ftp_port,
                    username=ftp_username,
                    password=ftp_password,
                    timeout=30,
                    allow_agent=False,
                    look_for_keys=False
                )

                print(f"SSH connected successfully")
                app.logger.info("Connected to sFTP server successfully")

                # Open SFTP session
                sftp = ssh.open_sftp()

                # Create remote directory if it doesn't exist
                try:
                    sftp.chdir(ftp_remote_path)
                except IOError:
                    # Directory doesn't exist, create it
                    dirs = []
                    current_path = ftp_remote_path
                    while current_path and current_path != '/':
                        dirs.insert(0, current_path)
                        current_path = os.path.dirname(current_path)

                    for dir_path in dirs:
                        try:
                            sftp.stat(dir_path)
                        except IOError:
                            sftp.mkdir(dir_path)
                            print(f"Created remote directory: {dir_path}")

                    sftp.chdir(ftp_remote_path)

                print(f"Changed to remote directory: {ftp_remote_path}")
                app.logger.info(f"Changed to remote directory: {ftp_remote_path}")

                # Upload files
                for image_path in image_files:
                    try:
                        filename = os.path.basename(image_path)

                        # Check if file already exists on remote
                        try:
                            sftp.stat(filename)
                            print(f"Skipping (already exists): {filename}")
                            skipped += 1
                            continue
                        except IOError:
                            pass

                        # Upload the file
                        print(f"Uploading: {filename}")
                        sftp.put(image_path, filename)
                        transferred += 1

                    except Exception as e:
                        print(f"Error transferring {filename}: {str(e)}")
                        app.logger.error(f"Error transferring {filename}: {str(e)}")
                        errors += 1

                # Close connections
                sftp.close()
                ssh.close()

            finally:
                try:
                    sftp.close()
                except:
                    pass
                try:
                    ssh.close()
                except:
                    pass

        else:
            # Regular FTP transfer
            from ftplib import FTP

            ftp = None
            try:
                print(f"Attempting FTP connection...")
                ftp = FTP()
                ftp.connect(ftp_server, ftp_port, timeout=30)
                ftp.login(ftp_username, ftp_password)

                print(f"FTP connected successfully")
                app.logger.info("Connected to FTP server successfully")

                # Create and change to remote directory
                try:
                    ftp.cwd(ftp_remote_path)
                except:
                    # Try to create the directory
                    dirs = ftp_remote_path.strip('/').split('/')
                    current = ''
                    for dir_name in dirs:
                        current += '/' + dir_name
                        try:
                            ftp.cwd(current)
                        except:
                            try:
                                ftp.mkd(current)
                                ftp.cwd(current)
                                print(f"Created remote directory: {current}")
                            except Exception as e:
                                print(f"Could not create directory {current}: {str(e)}")

                print(f"Changed to remote directory: {ftp_remote_path}")
                app.logger.info(f"Changed to remote directory: {ftp_remote_path}")

                # Get list of existing files
                existing_files = []
                try:
                    existing_files = ftp.nlst()
                except:
                    pass

                # Upload files
                for image_path in image_files:
                    try:
                        filename = os.path.basename(image_path)

                        # Check if file already exists
                        if filename in existing_files:
                            print(f"Skipping (already exists): {filename}")
                            skipped += 1
                            continue

                        # Upload the file
                        print(f"Uploading: {filename}")
                        with open(image_path, 'rb') as f:
                            ftp.storbinary(f'STOR {filename}', f)
                        transferred += 1

                    except Exception as e:
                        print(f"Error transferring {filename}: {str(e)}")
                        app.logger.error(f"Error transferring {filename}: {str(e)}")
                        errors += 1

                # Close connection
                ftp.quit()

            except Exception as e:
                if ftp:
                    try:
                        ftp.quit()
                    except:
                        pass
                raise

        print("="*80)
        print(f"Transfer complete: {transferred} uploaded, {skipped} skipped, {errors} errors")
        print("="*80)
        app.logger.info(f"Transfer complete: {transferred} uploaded, {skipped} skipped, {errors} errors")

        return jsonify({
            "status": "success",
            "message": f"Transfer complete: {transferred} uploaded, {skipped} skipped, {errors} errors",
            "transferred": transferred,
            "skipped": skipped,
            "errors": errors
        })

    except ImportError as e:
        error_msg = f"Required library not installed: {str(e)}"
        print(error_msg)
        app.logger.error(error_msg)
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500
    except Exception as e:
        error_msg = f"{protocol.upper() if 'protocol' in locals() else 'FTP'} transfer failed: {str(e)}"
        print(error_msg)
        app.logger.error(error_msg)
        import traceback
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": error_msg
        }), 500
