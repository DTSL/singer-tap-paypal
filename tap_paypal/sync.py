"""Sync data."""
# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import singer
from singer.catalog import Catalog, CatalogEntry

from tap_paypal import tools
from tap_paypal.paypal import PayPal
from tap_paypal.streams import STREAMS

LOGGER: logging.RootLogger = singer.get_logger()


def sync(
    paypal: PayPal,
    state: dict,
    catalog: Catalog,
    start_date: str,
    catchup_days: int,
    schemaless: bool,
) -> None:
    """Sync data from tap source.

    Arguments:
        paypal {PayPal} -- PayPal client
        state {dict} -- Tap state
        catalog {Catalog} -- Stream catalog
        start_date {str} -- Start date
    """
    # For every stream in the catalog
    LOGGER.info('Sync')
    LOGGER.debug('Current state:\n{state}')

    # Only selected streams are synced, whether a stream is selected is
    # determined by whether the key-value: "selected": true is in the schema
    # file.
    for stream in catalog.get_selected_streams(state):
        LOGGER.info(f'Syncing stream: {stream.tap_stream_id}')

        # Update the current stream as active syncing in the state
        singer.set_currently_syncing(state, stream.tap_stream_id)

        # Retrieve the state of the stream
        stream_state: dict = tools.get_stream_state(
            state,
            start_date,
            stream.tap_stream_id,
        )

        LOGGER.debug(f'Stream state: {stream_state}')

        # Write the schema
        singer.write_schema(
            stream_name=stream.tap_stream_id,
            schema=stream.schema.to_dict(),
            key_properties=stream.key_properties,
        )

        # Every stream has a corresponding method in the PayPal object e.g.:
        # The stream: paypal_transactions will call: paypal.paypal_transactions
        tap_data: Callable = getattr(paypal, stream.tap_stream_id)

        # The tap_data method yields rows of data from the API
        # The state of the stream is used as kwargs for the method
        # E.g. if the state of the stream has a key 'start_date', it will be
        # used in the method as start_date='2021-01-01T00:00:00+0000'
        for row in tap_data(catchup_days, schemaless, **stream_state):
            sync_record(stream, row, state)


def sync_record(stream: CatalogEntry, row: dict, state: dict) -> None:
    """Sync the record.

    Arguments:
        stream {CatalogEntry} -- Stream catalog
        row {dict} -- Record
        state {dict} -- State
    """
    # Retrieve the value of the bookmark
    bookmark: Optional[str] = tools.retrieve_bookmark_with_path(
        stream.replication_key,
        row,
    )

    # Write a row to the stream
    singer.write_record(
        stream.tap_stream_id,
        row,
        time_extracted=datetime.now(timezone.utc),
    )

    if bookmark:
        # Save the bookmark to the state
        singer.write_bookmark(
            state,
            stream.tap_stream_id,
            STREAMS[stream.tap_stream_id]['bookmark'],
            bookmark,
        )

        # Clear currently syncing
        tools.clear_currently_syncing(state)

        # Write the bootmark
        singer.write_state(state)
