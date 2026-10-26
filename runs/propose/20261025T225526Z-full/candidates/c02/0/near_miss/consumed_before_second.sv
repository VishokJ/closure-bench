`timescale 1ns / 1ps
module tb;
  logic        clk = 1'b0;
  logic        rst = 1'b0;
  logic        rxd = 1'b1;
  logic        m_axis_tready = 1'b0;
  logic [15:0] prescale = 16'd2;
  wire  [7:0]  m_axis_tdata;
  wire         m_axis_tvalid, busy, overrun_error, frame_error;

  always #4 clk = ~clk;

  uart_rx dut (
    .clk(clk), .rst(rst),
    .m_axis_tdata(m_axis_tdata), .m_axis_tvalid(m_axis_tvalid),
    .m_axis_tready(m_axis_tready),
    .rxd(rxd),
    .busy(busy), .overrun_error(overrun_error), .frame_error(frame_error),
    .prescale(prescale)
  );

  int ovr_cnt = 0;
  int fe_cnt = 0;
  bit consumed = 1'b0;
  bit busy_at_consume = 1'b0;

  always @(negedge clk) begin
    if (overrun_error) ovr_cnt++;
    if (frame_error) fe_cnt++;
  end

  task automatic send_byte(input logic [7:0] b);
    int bit_clks;
    bit_clks = int'(prescale) * 8;
    rxd = 1'b0; repeat (bit_clks) @(negedge clk);
    for (int i = 0; i < 8; i++) begin
      rxd = b[i]; repeat (bit_clks) @(negedge clk);
    end
    rxd = 1'b1; repeat (bit_clks) @(negedge clk);
  endtask

  initial begin
    @(negedge clk);
    rst = 1'b1; repeat (2) @(negedge clk);
    rst = 1'b0; repeat (2) @(negedge clk);

    send_byte(8'h3C);
    repeat (4) @(negedge clk);
    if (!(m_axis_tvalid && m_axis_tdata == 8'h3C))
      $fatal(1, "first word not presented: tvalid=%b tdata=%02h", m_axis_tvalid, m_axis_tdata);

    // Second frame, but the first word is read mid-frame (one cycle of tready)
    fork
      send_byte(8'hA5);
      begin
        repeat (3 * int'(prescale) * 8) @(negedge clk);
        if (!m_axis_tvalid) $fatal(1, "first word vanished before read");
        m_axis_tready = 1'b1;
        @(negedge clk);
        m_axis_tready = 1'b0;
        consumed = !m_axis_tvalid;
        busy_at_consume = busy;
      end
    join
    repeat (4) @(negedge clk);

    if (!consumed) $fatal(1, "first word was not consumed mid-frame");
    if (!busy_at_consume) $fatal(1, "read did not happen during the second frame");
    if (!(m_axis_tvalid && m_axis_tdata == 8'hA5))
      $fatal(1, "second word not presented: tvalid=%b tdata=%02h", m_axis_tvalid, m_axis_tdata);
    if (ovr_cnt != 0) $fatal(1, "overrun_error fired though first word was read");
    if (fe_cnt != 0) $fatal(1, "unexpected frame_error");

    $display("NEAR-MISS done: no overrun");
    $finish;
  end

  initial begin
    #1ms;
    $fatal(1, "timeout");
  end
endmodule
