import io
import logging

import oss2
import argparse
import pickle
from datetime import datetime, timezone
from typing import List, Dict


class OSS2Client:
    def __init__(self):
        access_key_id = "..."
        access_key_secret = "..."
        # endpoint = "oss-us-west-1-internal.aliyuncs.com"  # Example: 'oss-cn-hangzhou.aliyuncs.com'
        bucket_name = "..."
        # Create an OSS Auth instance
        self.auth = oss2.Auth(access_key_id, access_key_secret)
        # Create a Bucket instance
        self.bucket = oss2.Bucket(self.auth, endpoint, bucket_name)

    def put_object(self, object_name: str, file_name: str):
        with open(file_name, "rb") as file_data:
            self.bucket.put_object(object_name, file_data)

    def put_object_from_file(self, object_name: str, file_name: str):
        self.bucket.put_object_from_file(object_name, file_name)

    def copy_object_among_oss2(self, source_object_name: str, target_object_name: str):
        self.bucket.copy_object(
            self.bucket.bucket_name, source_object_name, target_object_name
        )

    def get_pickle_object(self, object_name: str):
        pickle_bytes = self.bucket.get_object(object_name).read()
        return pickle.load(io.BytesIO(pickle_bytes))

    def get_object_meta(self, object_name: str):
        if not self.object_exists(object_name):
            print("Object key not found")
            return None, None
        object_meta = self.bucket.get_object_meta(object_name)
        last_modified = object_meta.headers["Last-Modified"]
        file_size = f"{round(object_meta.content_length/ pow(10, 6), 2)} M"
        return last_modified, file_size

    def object_exists(self, object_name: str):
        try:
            self.bucket.get_object_meta(object_name)
            return True
        except Exception as ex:
            print(ex)
            return False

    def delete_object(self, object_name: str):
        self.bucket.delete_object(object_name)

    def get_folder_meta(self, folder_prefix: str):
        if not self.folder_exists(folder_prefix):
            print("Folder key not found")
            return None
        object_iter = oss2.ObjectIterator(self.bucket, folder_prefix, max_keys=1)
        for object in object_iter:
            print(object.key)
            print(self.get_object_meta(object.key))

    def get_latest_sub_object(self, folder_prefix: str, to_match: str = None):
        if not self.folder_exists(folder_prefix):
            print("Folder key not found")
            return None
        object_iter = oss2.ObjectIterator(self.bucket, folder_prefix, max_keys=1)
        object2last_modified: Dict = {}
        for object in object_iter:
            if to_match is not None and not to_match in object.key:
                continue
            object2last_modified[object.key] = datetime.strptime(
                self.bucket.get_object_meta(object.key).headers["Last-Modified"],
                "%a, %d %b %Y %H:%M:%S %Z",
            ).timestamp()
        if len(object2last_modified) == 0:
            return None
        sorted_list: List = sorted(
            object2last_modified.items(), key=lambda item: item[1], reverse=True
        )
        return sorted_list[0][0]

    def folder_exists(self, folder_prefix: str):
        try:
            objects: List = list(
                oss2.ObjectIterator(self.bucket, folder_prefix, max_keys=1)
            )
            if objects:
                return True
            else:
                return False
        except Exception as ex:
            print(ex)
            return False

    def copy_folder_among_oss2(self, source_folder_name: str, target_folder_name: str):
        for obj in oss2.ObjectIterator(self.bucket, prefix=source_folder_name):
            # Define the new destination key
            destination_key: str = (
                target_folder_name + obj.key[len(source_folder_name) :]
            )

            # Copy the object
            self.bucket.copy_object(self.bucket.bucket_name, obj.key, destination_key)

    def delete_subfolder_by_ts(self, folder_prefix: str, time_stamp: str):
        objects_to_delete = []
        time_stamp_date = datetime.strptime(time_stamp, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        for object in oss2.ObjectIterator(self.bucket, prefix=folder_prefix):
            last_modified = self.bucket.get_object_meta(object.key).headers[
                "Last-Modified"
            ]
            last_modified_date = datetime.strptime(
                last_modified, "%a, %d %b %Y %H:%M:%S %Z"
            ).replace(tzinfo=timezone.utc)
            if last_modified_date < time_stamp_date and object.key != folder_prefix:
                objects_to_delete.append(object.key)

        if objects_to_delete:
            delete_result = self.bucket.batch_delete_objects(objects_to_delete)
